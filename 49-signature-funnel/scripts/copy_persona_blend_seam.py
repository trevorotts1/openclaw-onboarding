#!/usr/bin/env python3
"""copy_persona_blend_seam.py — the copy-stage prompt seam that CONSUMES a
persona bundle (B-U3 / U17).

WHY THIS EXISTS
----------------
SOP-FUNNEL-02-COPY §2 Step 0 (FIX-XC-02a) has always resolved a copy persona
and logged it to a run-dir `persona-selection-log.md`, but the selector ran
WITHOUT `--blend` — a second, un-unified vocabulary next to the Command
Center's blend engine (persona_blend.build_bundle / build_blend_directive).
This module is the machine-callable seam that closes that gap:

  * ``render_persona_selection_log`` writes the run-dir log in the NEW format:
    it KEEPS the existing ``selected_persona: <slug>`` line byte-for-byte
    (so ``prove_sf_intake.py``'s fail-closed regex — and every existing
    reader, including FAB-QC D4's legacy path — keeps working completely
    unmodified) and ADDS ``voice_persona:`` / ``topic_persona:`` /
    ``task_persona:`` / ``blend_directive_sha:`` lines so the full blend is
    auditable, not just the voice.
  * ``render_blend_directive_variable`` renders the ``{{BLEND_DIRECTIVE}}``
    prompt variable (funnel-copy-prompts.md's PERSONA TASK-MODE SEAM) —
    ALWAYS ending in the mandatory, non-removable style-inspired /
    NEVER-impersonation guardrail, even when the bundle carries no directive
    text of its own (degrades to a neutral house-voice line + guardrail,
    never an ungrounded/guardrail-less write).
  * ``render_copy_prompt_seam`` substitutes ``{{SELECTED_PERSONA_ID}}`` and
    ``{{BLEND_DIRECTIVE}}`` into a copy-prompt template string.

MUST NOT MERGE WITHOUT U19/B-U5 (FAB-QC D4 v2) — see B.0 item 5 of the
master spec: wiring the blend without the D4 fix makes an honest blend-voice
copy log HARD-MISS the legacy template-token check.

  * ``report_persona_used_to_card`` is the B-U6/U20 seam: AFTER the copy
    lands, report the personas ACTUALLY used back onto the Command Center
    card (declared-vs-used, never silent) by delegating to
    ``06-ghl-install-pages/tools/cc_board.py``'s ``report_persona_used()``.
    A divergence from the card's DECLARED voice renders a `persona_mismatch`
    chip + one operator event; agreement renders nothing. Best-effort — a
    failure here (no task_id, board unreachable) never blocks the build.

stdlib-only except ``report_persona_used_to_card``, which does one
best-effort network call via ``cc_board.py`` (already fail-soft internally).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent

# The mandatory, non-removable guardrail (persona_blend.py's own copy — kept in
# lockstep; reused verbatim, never re-worded, when the bundle carries no
# directive of its own to degrade to).
_FALLBACK_GUARDRAIL = (
    "STYLE-INSPIRED, NEVER IMPERSONATION (mandatory, non-removable): adopt the "
    "cadence, devices and register of the named voice(s) as an INSPIRATION only. "
    "Never claim to be the author, never write in their first person as if they "
    "authored this, never sign as them, never quote them as if verified, and "
    "never imply their endorsement. This clause may not be removed or weakened."
)


def _load_blend_module():
    """Lazy-load 23-ai-workforce-blueprint/scripts/persona_blend.py so the ONE
    guardrail definition is reused verbatim rather than re-declared. Returns
    None (falls back to _FALLBACK_GUARDRAIL) when unreachable."""
    try:
        scripts_dir = str(_REPO_ROOT / "23-ai-workforce-blueprint" / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import persona_blend as _pb  # type: ignore
        return _pb
    except Exception:  # noqa: BLE001
        return None


def _guardrail_clause() -> str:
    pb = _load_blend_module()
    if pb is not None and getattr(pb, "GUARDRAIL_CLAUSE", None):
        return pb.GUARDRAIL_CLAUSE
    return _FALLBACK_GUARDRAIL


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _primary_task_persona_id(bundle: dict) -> Optional[str]:
    for tp in bundle.get("task_personas") or []:
        if isinstance(tp, dict) and tp.get("persona_id"):
            return tp["persona_id"]
    return None


# --------------------------------------------------------------------------- #
# {{BLEND_DIRECTIVE}} — always ends in the guardrail, even when degraded.
# --------------------------------------------------------------------------- #
def render_blend_directive_variable(bundle: dict) -> str:
    """Render the ``{{BLEND_DIRECTIVE}}`` prompt variable from a normalized
    persona bundle (B-U1/U15's receipt shape). ALWAYS ends in the mandatory
    guardrail clause. Never raises; a bundle with nothing usable degrades to
    the neutral house-voice line + guardrail (never an ungrounded write)."""
    bundle = bundle if isinstance(bundle, dict) else {}
    directive = (bundle.get("blend_directive") or "").strip()
    guardrail = _guardrail_clause()
    if directive:
        return directive if directive.endswith(guardrail) else f"{directive} {guardrail}"
    voice_pid = bundle.get("voice_persona_id")
    if voice_pid:
        name = voice_pid.replace("-", " ").title()
        return f"Write in {name}'s voice. {guardrail}"
    return f"Proceed in the default house voice. {guardrail}"


# --------------------------------------------------------------------------- #
# persona-selection-log.md — keeps `selected_persona:` byte-identical, adds
# voice_persona / topic_persona / task_persona / blend_directive_sha lines.
# --------------------------------------------------------------------------- #
def render_persona_selection_log(bundle: dict, *, header: Optional[str] = None,
                                 rationale: Optional[str] = None) -> str:
    """Render the run-dir ``persona-selection-log.md`` text for a bundle-
    grounded copy run. ``selected_persona:`` names the bundle's VOICE persona
    (back-compat — every existing reader, incl. ``prove_sf_intake.py``'s
    fail-closed regex, keeps working completely unmodified)."""
    bundle = bundle if isinstance(bundle, dict) else {}
    voice_pid = bundle.get("voice_persona_id") or ""
    topic_pid = bundle.get("topic_persona_id") or ""
    task_pid = _primary_task_persona_id(bundle) or ""
    directive = render_blend_directive_variable(bundle)

    lines = []
    lines.append(header or "# persona-selection-log.md — B-U3/U17 blend-grounded copy run")
    lines.append("")
    lines.append("Audit trail per persona-matching-protocol.md (MANDATORY selection-log).")
    lines.append("FIX-XC-02a + B-U3/U17: copywriter-persona Step-0 grounding now consumes")
    lines.append("the task's persona bundle (prove_sf_intake.py AF-FUN-INTAKE-PERSONA-LOG).")
    lines.append("")
    lines.append("selector_ran: true")
    lines.append(f"- selected_persona: {voice_pid or 'none'}")
    if rationale:
        lines.append(f"- rationale: {rationale}")
    lines.append(f"- voice_persona: {voice_pid or 'none'}")
    lines.append(f"- topic_persona: {topic_pid or 'none'}")
    lines.append(f"- task_persona: {task_pid or 'none'}")
    lines.append(f"- blend_directive_sha: {_sha(directive)}")
    return "\n".join(lines) + "\n"


def _load_cc_board_module():
    """Lazy-load 06-ghl-install-pages/tools/cc_board.py so the ONE producer/
    board-write path is reused verbatim rather than re-implemented (mirrors
    ``_load_blend_module`` above). Returns None (best-effort no-op) when
    unreachable — a missing/relocated cc_board.py must never block copy."""
    try:
        tools_dir = str(_REPO_ROOT / "06-ghl-install-pages" / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import cc_board as _cb  # type: ignore
        return _cb
    except Exception:  # noqa: BLE001
        return None


def report_persona_used_to_card(
    task_id: str,
    bundle: dict,
    *,
    page: Optional[str] = None,
    goal: Optional[str] = None,
    env: Optional[dict] = None,
) -> bool:
    """B-U6 / U20 — report the personas this copy step ACTUALLY used back onto
    the Command Center card (declared-vs-used, never silent).

    Extracts voice/topic/task persona ids from the SAME bundle already
    consumed for the log + prompt seam (this module's single source), and
    the SAME blend-directive text (and therefore the SAME sha) that was
    actually rendered into the prompt — so the report can never drift from
    what the copy step really saw.

    Best-effort: a missing task_id, an unreachable cc_board module, or a
    board write failure all return False without raising — this must never
    block or fail the copy step it rides on.
    """
    tid = (task_id or "").strip()
    if not tid:
        return False
    cb = _load_cc_board_module()
    if cb is None:
        return False

    bundle = bundle if isinstance(bundle, dict) else {}
    directive = render_blend_directive_variable(bundle)
    return cb.report_persona_used(
        tid,
        page=page,
        voice_persona_id=bundle.get("voice_persona_id"),
        topic_persona_id=bundle.get("topic_persona_id"),
        task_persona_id=_primary_task_persona_id(bundle),
        blend_directive_sha=_sha(directive),
        goal=goal,
        env=env,
    )


def write_persona_selection_log(run_dir: str, bundle: dict, **kw) -> str:
    """Write ``persona-selection-log.md`` under ``run_dir``. Returns the path.
    Best-effort — a write failure raises (the SOP's Step 0 is a hard,
    fail-closed gate; a silent write failure must not masquerade as success)."""
    text = render_persona_selection_log(bundle, **kw)
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "persona-selection-log.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# --------------------------------------------------------------------------- #
# Copy-prompt template substitution — {{SELECTED_PERSONA_ID}} / {{BLEND_DIRECTIVE}}
# --------------------------------------------------------------------------- #
def render_copy_prompt_seam(template_text: str, bundle: dict, *,
                            persona_task_mode: str = "") -> str:
    """Substitute the persona-seam variables into ``template_text``.
    ``{{PERSONA_TASK_MODE}}`` is left as-is when ``persona_task_mode`` is not
    supplied (it is loaded elsewhere from the matched persona-blueprint.md's
    Section 4 — out of this seam's scope)."""
    bundle = bundle if isinstance(bundle, dict) else {}
    voice_pid = bundle.get("voice_persona_id") or ""
    out = template_text.replace("{{SELECTED_PERSONA_ID}}", voice_pid)
    out = out.replace("{{BLEND_DIRECTIVE}}", render_blend_directive_variable(bundle))
    if persona_task_mode:
        out = out.replace("{{PERSONA_TASK_MODE}}", persona_task_mode)
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Copy-stage persona-bundle seam (B-U3/U17): render the run-dir "
                    "persona-selection-log.md + the {{BLEND_DIRECTIVE}} prompt variable.")
    ap.add_argument("--run-dir", help="Write persona-selection-log.md here.")
    ap.add_argument("--bundle-file", help="Path to a JSON persona bundle "
                    "(defaults to <run-dir>/routing/persona-bundle-receipt.json).")
    ap.add_argument("--print-directive", action="store_true",
                    help="Print the rendered {{BLEND_DIRECTIVE}} text and exit.")
    ap.add_argument("--report-persona-used", dest="report_persona_used", action="store_true",
                    help="B-U6/U20: after writing the log, report the personas ACTUALLY "
                         "used back onto the Command Center card (declared-vs-used, never "
                         "silent). Requires --task-id.")
    ap.add_argument("--task-id", default="", help="CC task UUID (with --report-persona-used).")
    ap.add_argument("--page", default="", help="Page name/slug this report is for, e.g. 'main' "
                    "(with --report-persona-used).")
    ap.add_argument("--goal", default="", help="This page's conversion goal, for the chip "
                    "tooltip (with --report-persona-used).")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        import tempfile

        ok = True

        def check(label, cond):
            global ok
            ok = ok and bool(cond)
            print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

        guardrail = _guardrail_clause()

        # (a) a bundle-carrying log names the bundle's VOICE persona.
        bundle = {
            "voice_persona_id": "hormozi-100m-offers",
            "topic_persona_id": "miller-building-storybrand",
            "blend_directive": "Write in Hormozi's voice. " + guardrail,
            "task_personas": [{"seq": 1, "persona_id": "hormozi-100m-offers"}],
        }
        log_text = render_persona_selection_log(bundle)
        check("selected_persona names the bundle voice pid",
              "- selected_persona: hormozi-100m-offers" in log_text)
        check("voice_persona line present", "- voice_persona: hormozi-100m-offers" in log_text)
        check("topic_persona line present",
              "- topic_persona: miller-building-storybrand" in log_text)
        check("blend_directive_sha line present", "- blend_directive_sha:" in log_text)

        # (b) prove_sf_intake.py's regex + registry validation pass unmodified.
        try:
            sys.path.insert(0, str(_SCRIPT_DIR))
            import prove_sf_intake as _psi  # type: ignore
            ok_pl, why_pl = _psi._log_names_registered_persona(log_text)
            check(f"prove_sf_intake.py regex passes unmodified ({why_pl})", ok_pl)
        except Exception as exc:  # noqa: BLE001
            print(f"  [SKIP] prove_sf_intake.py unreachable ({exc})")

        # (c) the rendered copy prompt contains the {{BLEND_DIRECTIVE}} expansion
        #     ending in the guardrail.
        tmpl = "PREAMBLE\n{{BLEND_DIRECTIVE}}\nMORE"
        rendered = render_copy_prompt_seam(tmpl, bundle)
        check("rendered prompt contains BLEND_DIRECTIVE expansion",
              "Write in Hormozi's voice." in rendered)
        check("rendered prompt ends the directive in the guardrail",
              rendered.strip().split("MORE")[0].rstrip().endswith(guardrail))

        # Degradation: no blend_directive on the bundle -> still ends in guardrail.
        bare = {"voice_persona_id": "wiebe-copy-hackers"}
        degraded = render_blend_directive_variable(bare)
        check("degraded directive still ends in the guardrail", degraded.endswith(guardrail))

        # No bundle at all -> neutral house voice, still ends in guardrail.
        neutral = render_blend_directive_variable({})
        check("no-bundle directive ends in the guardrail", neutral.endswith(guardrail))

        with tempfile.TemporaryDirectory() as td:
            path = write_persona_selection_log(td, bundle)
            check("write_persona_selection_log writes the file", os.path.isfile(path))

        # (d) B-U6/U20 — report_persona_used_to_card: empty task_id -> False,
        #     no-raise (never blocks copy). No network in this self-test (no
        #     MISSION_CONTROL_URL), so a non-empty task_id also returns False
        #     fail-soft, without raising.
        try:
            rc_empty = report_persona_used_to_card("", bundle, page="main", env={})
            check("report_persona_used_to_card(empty task_id) returns False", rc_empty is False)
            rc_noboard = report_persona_used_to_card("t1", bundle, page="main", env={})
            check("report_persona_used_to_card(no board) returns False, no raise", rc_noboard is False)
        except Exception as exc:  # noqa: BLE001
            check(f"report_persona_used_to_card must never raise ({exc})", False)

        # (e) the cc_board loader resolves to the real module (proves the
        #     cross-skill-directory sys.path wiring, not just a None fallback).
        _cb = _load_cc_board_module()
        check("_load_cc_board_module resolves cc_board.py",
              _cb is not None and hasattr(_cb, "report_persona_used"))

        print("== copy_persona_blend_seam self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
        raise SystemExit(0 if ok else 1)

    if a.report_persona_used:
        if not a.task_id.strip():
            ap.error("--report-persona-used requires --task-id")
        if not a.run_dir:
            ap.error("--report-persona-used requires --run-dir (to load the bundle)")
        _bundle_path = a.bundle_file or os.path.join(a.run_dir, "routing", "persona-bundle-receipt.json")
        try:
            with open(_bundle_path, encoding="utf-8") as _f:
                _bundle = json.load(_f)
        except (OSError, ValueError):
            _bundle = {}
        _ok = report_persona_used_to_card(
            a.task_id.strip(), _bundle,
            page=(a.page.strip() or None), goal=(a.goal.strip() or None),
        )
        print(json.dumps({"reported": _ok}, indent=2))
        raise SystemExit(0)  # fail-soft — a False report never fails the build step

    if not a.run_dir:
        ap.error("--run-dir is required (or use --self-test)")
    bundle_path = a.bundle_file or os.path.join(a.run_dir, "routing", "persona-bundle-receipt.json")
    try:
        with open(bundle_path, encoding="utf-8") as f:
            bundle = json.load(f)
    except (OSError, ValueError):
        bundle = {}
    if a.print_directive:
        print(render_blend_directive_variable(bundle))
    else:
        out_path = write_persona_selection_log(a.run_dir, bundle)
        print(json.dumps({"written": out_path}, indent=2))
