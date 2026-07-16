#!/usr/bin/env python3
"""daily_blend_bundle.py — Skill 35 (social-media-planner) PER-DAY blend
selection via the U5 scoped-bundle mechanism (Skill 6 U98, D1 binding ruling).

WHY THIS EXISTS
----------------
Before this module, playbook.md Step 0a.5 selected ONE persona to "govern
this week's content" (a single-persona-per-week pick, logged once to
persona-selection-log.md) and every day of the 7-day cycle inherited that
one voice. Per the D1 binding ruling ("THE BLENDED PERSONA GOVERNS EVERY
ENGINE — NO EXEMPTIONS, NEVER ADVISORY") the blend directive must govern
each day's copy, and U5 already shipped the exact mechanism this needed:
`persona_blend.build_bundle(..., scope_hint={...})` — a per-scope blend
bundle keyed by `(task_id, scope)`, previously wired for per-PAGE funnel
copy (A-U5). This module is Skill 35's adoption of that SAME mechanism for
per-DAY social content: one scope per posting day (`day-1` .. `day-7`),
never a re-implementation of the blend logic itself.

WHAT THIS DOES NOT CHANGE
--------------------------
The Television Show Framework (Day 1 hooks, escalating pitch intensity,
Day 7 grand finale) is untouched — this module only resolves WHO governs
the VOICE for each day's copy and logs the decision; the content-creation
steps (research, image generation, publishing) are unchanged.

FLAG-GUARDED (revert path per U98's spec)
------------------------------------------
`SKILL35_BLEND_GOVERNS` env var, default enabled ("1"). Setting it to "0"
restores the pre-U98 behavior exactly: `build_week_bundles` then raises
`LegacyWeeklyPersonaRequired` rather than silently emitting a governed
bundle, so a caller on the reverted flag is forced back onto the
pre-existing (prose-level, playbook.md Step 0a.5) single-persona-per-week
selection instead of getting a half-migrated result.

stdlib-only, deterministic, hermetic-testable via the same
`PERSONA_FOR_JOB_FIXTURE` / paths-dict escape hatches persona_blend.py and
persona_for_job.py already use.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_BLEND_SCRIPT = _REPO / "23-ai-workforce-blueprint" / "scripts" / "persona_blend.py"

FLAG_ENV = "SKILL35_BLEND_GOVERNS"
DEFAULT_DEPARTMENT = "social-media"
DAY_COUNT = 7


class LegacyWeeklyPersonaRequired(RuntimeError):
    """Raised when SKILL35_BLEND_GOVERNS=0 (the flag-guarded revert path).

    Restores pre-U98 behavior exactly: the caller must fall back to
    playbook.md Step 0a.5's original single-persona-per-week selection
    (prose-level; this module intentionally does not re-implement it)."""


def blend_governs() -> bool:
    return os.environ.get(FLAG_ENV, "1").strip() != "0"


def _load_persona_blend():
    """Path-import persona_blend.py (23-ai-workforce-blueprint/scripts is not
    a package; mirrors the loader pattern shared-utils/tone_persona_autopick.py
    and persona_blend.py itself already use for hyphenated/foreign paths)."""
    candidates = [
        os.environ.get("PERSONA_BLEND_PATH", "").strip(),
        str(_BLEND_SCRIPT),
        str(Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint"
            / "scripts" / "persona_blend.py"),
        "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/persona_blend.py",
    ]
    for cand in candidates:
        if cand and Path(cand).exists():
            spec = importlib.util.spec_from_file_location("persona_blend_s35", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    return None


def day_scope_hint(day_number: int, weekly_theme: str = "", conversion_goal: str = "") -> dict:
    """The scope_hint for ONE posting day. `page_role` doubles as the topic
    signal (build_bundle's A-U5 tie-breaker) so distinct days can resolve
    distinct topic persona picks, never a forced-identical blend."""
    if not (1 <= day_number <= DAY_COUNT):
        raise ValueError(f"day_number must be 1..{DAY_COUNT}, got {day_number!r}")
    hint = {"page_role": f"day-{day_number}", "page_slug": f"day-{day_number}"}
    if conversion_goal:
        hint["conversion_goal"] = conversion_goal
    return hint


def build_daily_bundle(day_number: int, weekly_theme: str, *,
                        department: str = DEFAULT_DEPARTMENT,
                        paths: dict = None, db_path=None,
                        use_llm: bool = True, record: bool = True,
                        conversion_goal: str = "") -> dict:
    """Resolve ONE day's GOVERNING blend bundle via the U5 scoped-bundle
    mechanism. Returns the bundle dict verbatim from persona_blend.build_bundle
    (blend_directive / voice / rationale / scope / scope_hint all present).

    Raises LegacyWeeklyPersonaRequired when SKILL35_BLEND_GOVERNS=0.
    """
    if not blend_governs():
        raise LegacyWeeklyPersonaRequired(
            f"{FLAG_ENV}=0 — revert to playbook.md Step 0a.5's pre-U98 "
            f"single-persona-per-week selection (not re-implemented here).")
    pb = _load_persona_blend()
    if pb is None:
        raise RuntimeError("persona_blend.py not reachable — cannot resolve a "
                            "governed daily bundle (never silently degrade to "
                            "an ungoverned voice).")
    scope_hint = day_scope_hint(day_number, weekly_theme, conversion_goal)
    task = f"Day {day_number} social content for the weekly theme: {weekly_theme}"
    return pb.build_bundle(
        task, department, paths=paths, db_path=db_path, use_llm=use_llm,
        record=record, topic_hint=weekly_theme, conversion_goal=conversion_goal,
        scope_hint=scope_hint,
    )


def build_week_bundles(weekly_theme: str, *, run_dir=None,
                        department: str = DEFAULT_DEPARTMENT,
                        paths: dict = None, db_path=None,
                        use_llm: bool = True, record: bool = True,
                        conversion_goal: str = "",
                        day_count: int = DAY_COUNT) -> dict:
    """Resolve + log ALL 7 days' governing bundles for one weekly cycle.

    Returns {"days": [ {day, scope, bundle}, ... ], "governed": True,
             "flag": SKILL35_BLEND_GOVERNS value}. Each day is logged to
    `run_dir/persona-selection-log.md` (one entry per day, via
    persona_blend.write_persona_selection_log_entry) when run_dir is given —
    replaces the old ONE log line per week with ONE per day (U98 binary
    acceptance (a): "logged per day").
    """
    if not blend_governs():
        raise LegacyWeeklyPersonaRequired(
            f"{FLAG_ENV}=0 — revert to playbook.md Step 0a.5's pre-U98 "
            f"single-persona-per-week selection (not re-implemented here).")
    pb = _load_persona_blend()
    if pb is None:
        raise RuntimeError("persona_blend.py not reachable — cannot resolve "
                            "governed daily bundles.")
    days = []
    for n in range(1, day_count + 1):
        bundle = build_daily_bundle(
            n, weekly_theme, department=department, paths=paths, db_path=db_path,
            use_llm=use_llm, record=record, conversion_goal=conversion_goal)
        scope_key = bundle.get("scope") or f"day-{n}"
        if run_dir is not None:
            reason = bundle.get("rationale", {}).get("scope") or bundle.get(
                "rationale", {}).get("collapse", "")
            pb.write_persona_selection_log_entry(run_dir, scope_key, bundle,
                                                  reason=reason)
        days.append({"day": n, "scope": scope_key, "bundle": bundle})
    return {"days": days, "governed": True, "flag": os.environ.get(FLAG_ENV, "1")}


# --------------------------------------------------------------------------- #
# receipt — the fixture-run proof this unit's binary acceptance (a) demands
# --------------------------------------------------------------------------- #
GUARDRAIL_MARK = "STYLE-INSPIRED, NEVER IMPERSONATION"


def prove_daily_governance(weekly_theme: str = "founder resilience", *,
                            run_dir=None, day_count: int = DAY_COUNT,
                            paths: dict = None, db_path=None,
                            use_llm: bool = True, record: bool = True) -> dict:
    """Fixture-run receipt: proves EACH day's bundle carries a governed
    blend_directive (ends in the mandatory guardrail) traceable to that day's
    own bundle, AND that the 7 scope keys are genuinely distinct (never a
    forced-identical single call path). PASS/FAIL per day + overall."""
    result = build_week_bundles(weekly_theme, run_dir=run_dir, day_count=day_count,
                                paths=paths, db_path=db_path, use_llm=use_llm, record=record)
    checks = []
    scopes_seen = set()
    for row in result["days"]:
        bundle = row["bundle"]
        directive = bundle.get("blend_directive") or ""
        governed = bool(directive) and GUARDRAIL_MARK in directive
        distinct_scope = row["scope"] not in scopes_seen
        scopes_seen.add(row["scope"])
        checks.append({
            "day": row["day"], "scope": row["scope"],
            "governed": governed, "distinct_scope": distinct_scope,
            "pass": governed and distinct_scope,
        })
    overall = all(c["pass"] for c in checks) and len(scopes_seen) == day_count
    return {"weekly_theme": weekly_theme, "day_count": day_count,
            "checks": checks, "pass": overall,
            "distinct_scopes": len(scopes_seen)}


def main(argv: list) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Skill 35 per-day blend selection via U5 scoped bundles.")
    ap.add_argument("--theme", default="founder resilience")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--prove", action="store_true")
    a = ap.parse_args(argv)

    if a.self_test:
        return _self_test()
    if a.prove:
        print(json.dumps(prove_daily_governance(a.theme, run_dir=a.run_dir), indent=2))
        return 0
    result = build_week_bundles(a.theme, run_dir=a.run_dir)
    print(json.dumps(result, indent=2, default=str))
    return 0


def _hermetic_paths() -> dict:
    """A paths dict pointed at THIS repo's own shipped seed persona catalog
    (22-book-to-persona-coaching-leadership-system/persona-categories.json) —
    never a live ~/.openclaw workspace. Deterministic and identical on every
    checkout (CI included); company_config/soul_md are intentionally omitted
    (the selector degrades those to neutral defaults with a printed WARN,
    never a crash — see persona-selector-v2.load_company_config)."""
    seed = _REPO / "22-book-to-persona-coaching-leadership-system"
    return {
        "persona_categories": seed / "persona-categories.json",
        "coaching_personas": seed,
    }


def _self_test() -> int:
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    pb = _load_persona_blend()
    if pb is None:
        print("  [SKIP] persona_blend.py not reachable in this environment")
        return 0

    # Hermetic inputs: an explicit paths dict pinned to THIS repo's own seed
    # catalog (never a live ~/.openclaw workspace), and a sentinel db_path
    # that resolve_db.is_db_found() reports as not-found, short-circuit any
    # live-DB scan. This exercises the REAL persona_blend.build_bundle end to
    # end (the real selector, the real seed catalog, the real collapse/
    # decompose logic) — never a hand-rolled stub of this module's own
    # business logic — while staying deterministic and network/workspace-
    # free, the same posture persona_for_job.py's own --self-test uses via
    # PERSONA_FOR_JOB_FIXTURE.
    _hermetic_db = Path("/nonexistent/u98-hermetic-test-sentinel.db")
    _paths = _hermetic_paths()
    import tempfile
    _tmp_log = Path(tempfile.mkdtemp(prefix="u98-s35-selftest-")) / "match-score-log.jsonl"
    try:
        os.environ[FLAG_ENV] = "1"
        os.environ.pop("OPENCLAW_PERSONA_CATEGORIES", None)
        # log_match_score writes into paths['coaching_personas'] unconditionally
        # (independent of record=False, which only gates the decompose call) —
        # redirect it to a throwaway tempdir so a hermetic self-test run never
        # writes into this repo's tracked seed directory.
        os.environ["OPENCLAW_PERSONA_MATCH_SCORE_LOG"] = str(_tmp_log)
        result = build_week_bundles("founder resilience", paths=_paths, db_path=_hermetic_db,
                                    use_llm=False, record=False, day_count=7)
        check("7 days resolved", len(result["days"]) == 7)
        scopes = [d["scope"] for d in result["days"]]
        check("7 distinct scope keys", len(set(scopes)) == 7)
        check("scopes are day-1..day-7", scopes == [f"day-{n}" for n in range(1, 8)])
        for d in result["days"]:
            bundle = d["bundle"]
            check(f"day {d['day']} bundle carries scope_hint", bundle.get("scope") == d["scope"])
            directive = bundle.get("blend_directive") or ""
            check(f"day {d['day']} blend_directive carries the guardrail",
                  bool(directive) and GUARDRAIL_MARK in directive)
            check(f"day {d['day']} never touched the live DB",
                  bundle.get("db") == "none")

        proof = prove_daily_governance("founder resilience", day_count=7, paths=_paths,
                                       db_path=_hermetic_db, use_llm=False, record=False)
        check("prove_daily_governance overall PASS", proof["pass"])
        check("prove_daily_governance distinct_scopes == 7", proof["distinct_scopes"] == 7)

        os.environ[FLAG_ENV] = "0"
        raised = False
        try:
            build_week_bundles("founder resilience", paths=_paths, db_path=_hermetic_db)
        except LegacyWeeklyPersonaRequired:
            raised = True
        check("flag=0 reverts to LegacyWeeklyPersonaRequired (never a silent half-migration)", raised)
    finally:
        os.environ.pop(FLAG_ENV, None)
        os.environ.pop("OPENCLAW_PERSONA_MATCH_SCORE_LOG", None)
        try:
            import shutil
            shutil.rmtree(_tmp_log.parent, ignore_errors=True)
        except Exception:
            pass

    print("== daily_blend_bundle self-test: %s ==" % ("ALL PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
