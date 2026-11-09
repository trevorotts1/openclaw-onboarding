"""Focused tests — Skill 06 STANDALONE MARKETING QUIZ (WF34 / B21, IG-PAGE-01, IG-PAGE-02).

WHAT IS LOCKED IN HERE
----------------------
  B21        a marketing quiz is a SEPARATE contract from a course lesson quiz;
             outcomes, boundaries, branches and lead/field/tag/workflow effects
             are proved through the real deterministic scoring path.
  IG-PAGE-01 wireframes, mockups, design-style intake, copy/prompt budgets,
             native full-width, SEO and native checkout gates stay enforced.
  IG-PAGE-02 the intended contact, field, tag, result copy and workflow outcome
             are proved for every outcome against a SYNTHETIC browser/CRM fixture.

HERMETIC: no network, no browser, no GHL, no live writes, no real contact data.
The fixture is declared ``trust: FAKE`` and the coordinator refuses anything else
as proof. Live canary: NOT RUN.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent
_TOOLS_DIR = _SKILL_DIR / "tools"
for _p in (str(_TOOLS_DIR),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ghl_marketing_quiz_builder as qb  # noqa: E402

FIXTURES = _TESTS_DIR / "fixtures" / "marketing-quiz"
PLAN_PATH = FIXTURES / "plan.example.json"
FIXTURE_PATH = FIXTURES / "fake-browser-crm-acceptance.json"
CP01_PATH = FIXTURES / "cp01-interface.json"


def load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def plan() -> dict:
    return load(PLAN_PATH)


@pytest.fixture()
def fixture() -> dict:
    return load(FIXTURE_PATH)


# ---------------------------------------------------------------------------
# B21 — standalone marketing quiz, not a course lesson quiz
# ---------------------------------------------------------------------------
def test_b21_marketing_quiz_refuses_course_quiz_endpoints(plan):
    """A course/lesson quiz contract is never a stand-in for lead capture."""
    for declared in (
        {"rail": "courses.lessons.quiz"},
        {"rail": "managed_browser", "endpoint": "courses/lessons/1/quiz"},
        {"rail": "managed_browser", "operation_id": "course_lesson_quiz.create"},
        {"rail": "managed_browser", "transport": {"endpoint": "courses/1/lessons/2/quiz"}},
    ):
        with pytest.raises(qb.CourseQuizEndpointRefused):
            qb.normalize_plan({**plan, **declared})

    # The only accepted rail today: there is no verified public quiz contract.
    with pytest.raises(qb.CourseQuizEndpointRefused):
        qb.normalize_plan({**plan, "rail": "public_rest"})


def test_b21_every_outcome_boundary_is_reachable(plan):
    """Min and max of every outcome are produced through the real scoring path."""
    p = qb.normalize_plan(plan)
    assert qb.reachable_score_range(p) == (0, 11)

    rows = qb.outcome_boundaries(p)
    got = {(r["outcome"], r["boundary"], r["score"]) for r in rows}
    assert got == {
        ("starter", "min", 0), ("starter", "max", 3),
        ("builder", "min", 4), ("builder", "max", 7),
        ("operator", "min", 8), ("operator", "max", 11),
    }
    for row in rows:
        scored = qb.score_answers(p, row["answers"])
        assert scored["score"] == row["score"]
        assert scored["outcome"] == row["outcome"]


def test_b21_outcome_bands_must_be_contiguous_and_covered(plan):
    """A gap, an overlap, or a short tail is a refusal — never a silent fallback."""
    gap = copy.deepcopy(plan)
    gap["outcomes"][0]["score_max"] = 2          # leaves score 3 uncovered
    with pytest.raises(qb.QuizPlanInvalid):
        qb.normalize_plan(gap)

    short = copy.deepcopy(plan)
    short["outcomes"][-1]["score_max"] = 10      # reachable max is 11
    with pytest.raises(qb.QuizPlanInvalid):
        qb.normalize_plan(short)

    overlap = copy.deepcopy(plan)
    overlap["outcomes"][1]["score_min"] = 3      # starter already owns 3
    with pytest.raises(qb.QuizPlanInvalid):
        qb.normalize_plan(overlap)


def test_b21_router_beats_score_band(plan):
    """An explicit router answer outranks the score band (deterministic order)."""
    p = qb.normalize_plan(plan)
    # Score 4 would be 'builder', but the paid-ads router answers 'operator'.
    answers = {"q1": "a", "q2": "c", "q4": "a", "q5": "synthetic@example.test"}
    scored = qb.score_answers(p, answers)
    assert scored["score"] == 4
    assert scored["outcome"] == "operator"
    assert "q3" not in scored["path"]          # the branch skipped it


def test_b21_branching_must_be_forward(plan):
    backward = copy.deepcopy(plan)
    backward["questions"][1]["branch"] = {"when_choice": "c", "goto": "q1"}
    with pytest.raises(qb.QuizPlanInvalid):
        qb.normalize_plan(backward)

    unknown_choice = copy.deepcopy(plan)
    unknown_choice["questions"][1]["branch"] = {"when_choice": "zz", "goto": "q4"}
    with pytest.raises(qb.QuizPlanInvalid):
        qb.normalize_plan(unknown_choice)


def test_b21_branch_paths_and_required_fields_are_proved(plan, fixture):
    receipt = qb.verify_acceptance(plan, fixture)
    assert receipt["ok"], receipt["problems"]
    assert "branch_paths_verified" in receipt["checks"]
    assert "required_fields_enforced" in receipt["checks"]
    assert "outcome_boundaries_reachable" in receipt["checks"]
    assert "every_outcome_verified" in receipt["checks"]


# ---------------------------------------------------------------------------
# IG-PAGE-01 — page gates stay enforced
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mutate", [
    lambda p: p["page_gates"].__setitem__("native_full_width", False),
    lambda p: p["page_gates"].pop("mockups"),
    lambda p: p["page_gates"].pop("wireframes"),
    lambda p: p["page_gates"]["design_style_intake"].__setitem__("style", "freehand"),
    lambda p: p["page_gates"]["design_style_intake"].__setitem__("approved", False),
    lambda p: p["page_gates"]["copy_budget"].__setitem__("body_max", 0),
    lambda p: p["page_gates"]["seo"].__setitem__("title", "x" * (qb.SEO_TITLE_MAX + 1)),
    lambda p: p["page_gates"]["seo"].__setitem__("description", "x" * (qb.SEO_DESC_MAX + 1)),
    lambda p: p["page_gates"]["seo"].__setitem__("canonical", "http://insecure.test/x"),
    lambda p: p["page_gates"]["native_checkout"].__setitem__("bypassed", True),
    lambda p: p["page_gates"]["native_checkout"].__setitem__("mode", "raw_card_fields"),
])
def test_ig_page_01_page_gates_enforced(plan, mutate):
    broken = copy.deepcopy(plan)
    mutate(broken)
    with pytest.raises(qb.PageGateIncomplete):
        qb.normalize_plan(broken)


def test_ig_page_01_missing_gate_block_is_refused(plan):
    broken = copy.deepcopy(plan)
    del broken["page_gates"]
    with pytest.raises(qb.PageGateIncomplete):
        qb.normalize_plan(broken)


# ---------------------------------------------------------------------------
# IG-PAGE-02 — intended contact, field, tag, result and workflow outcome
# ---------------------------------------------------------------------------
def test_ig_page_02_lead_capture_and_routing(plan, fixture):
    p = qb.normalize_plan(plan)
    crm = copy.deepcopy(fixture["crm"])
    seen = set()
    for sub in fixture["submissions"]:
        effects = qb.compute_lead_effects(p, sub)
        assert effects["outcome"] == sub["expected_outcome"]
        assert effects["score"] == sub["expected_score"]
        # result copy is the plan's copy for that outcome
        expected_copy = next(o["result_copy"] for o in p["outcomes"]
                             if o["key"] == sub["expected_outcome"])
        assert effects["result_copy"] == expected_copy
        # tags: plan-level tag + the outcome tag, nothing else
        assert effects["tags"] == sub["expected_effect"]["tags"]
        # exactly the intended approved workflow for that outcome
        assert effects["workflows"] == sub["expected_effect"]["workflows"]
        # outcome/score/consent persisted as fields
        assert effects["fields"]["zhc_quiz_outcome"] == sub["expected_outcome"]
        assert effects["fields"]["zhc_quiz_score"] == sub["expected_score"]
        assert effects["fields"]["zhc_quiz_consent"] is True
        assert effects["contact"]["email"].endswith("@example.test")
        crm = qb.apply_submission_to_crm(crm, effects)
        seen.add(effects["outcome"])

    assert seen == {"starter", "builder", "operator"}
    assert len(crm["contacts"]) == len(fixture["submissions"])
    # one enrollment per contact, never a second workflow
    assert len(crm["enrollments"]) == len(fixture["submissions"])
    assert {e["workflow"] for e in crm["enrollments"]} == {
        "wf_quiz_starter", "wf_quiz_builder", "wf_quiz_operator"}


def test_ig_page_02_consent_blocks_unconsented_lead(plan, fixture):
    p = qb.normalize_plan(plan)
    sub = dict(fixture["submissions"][0])
    sub["consent"] = False
    with pytest.raises(qb.ConsentRequired):
        qb.compute_lead_effects(p, sub)

    missing_capture = dict(fixture["submissions"][0])
    missing_capture["capture"] = {}
    with pytest.raises(qb.CaptureIncomplete):
        qb.compute_lead_effects(p, missing_capture)


def test_ig_page_02_sensitive_capture_is_refused(plan):
    broken = copy.deepcopy(plan)
    broken["capture"]["fields"].append(
        {"field_key": "zhc_ssn", "source": "Social Security Number"})
    with pytest.raises(qb.SensitiveFieldRefused):
        qb.normalize_plan(broken)


def test_ig_page_02_unapproved_workflow_is_refused(plan):
    broken = copy.deepcopy(plan)
    broken["followup_workflows"][0]["approved"] = False
    with pytest.raises(qb.QuizPlanInvalid):
        qb.normalize_plan(broken)


def test_ig_page_02_render_and_result_copy_are_verified(plan, fixture):
    receipt = qb.verify_acceptance(plan, fixture)
    assert "render_and_result_copy_verified" in receipt["checks"]

    bad = copy.deepcopy(fixture)
    bad["browser"]["render"]["mobile"]["console_errors"] = ["TypeError: x is undefined"]
    assert not qb.verify_acceptance(plan, bad)["ok"]

    bad = copy.deepcopy(fixture)
    bad["browser"]["render"]["desktop"]["native_full_width"] = False
    assert not qb.verify_acceptance(plan, bad)["ok"]

    bad = copy.deepcopy(fixture)
    bad["browser"]["result_copy_rendered"]["builder"] = "a different result"
    assert not qb.verify_acceptance(plan, bad)["ok"]


def test_b21_fake_fixture_is_never_live_proof(plan, fixture):
    """A fixture that is not declared FAKE cannot be acceptance proof."""
    receipt = qb.verify_acceptance(plan, fixture)
    assert receipt["live"] is False
    assert receipt["trust"] == "FAKE"

    with pytest.raises(qb.FixtureNotSynthetic):
        qb.verify_acceptance(plan, {**fixture, "trust": "LIVE"})


def test_b21_uncovered_outcome_and_wrong_outcome_fail(plan, fixture):
    truncated = copy.deepcopy(fixture)
    truncated["submissions"] = truncated["submissions"][:4]   # drops operator
    receipt = qb.verify_acceptance(plan, truncated)
    assert not receipt["ok"]
    assert any("operator" in p for p in receipt["problems"])

    wrong = copy.deepcopy(fixture)
    wrong["submissions"][0]["expected_outcome"] = "builder"
    assert not qb.verify_acceptance(plan, wrong)["ok"]


# ---------------------------------------------------------------------------
# Execute plan, translation, dependency plan
# ---------------------------------------------------------------------------
def test_execute_plan_uses_the_dedicated_selector_file(plan):
    selectors = qb.load_selectors()
    assert selectors["objects"]["marketing_quiz"]["anchors"] == selectors["anchors"]

    steps = qb.build_step_plan(plan, selectors)
    assert len(steps["steps"]) == len(qb.STEP_DEFS)
    known = {a["id"] for a in selectors["anchors"]}
    assert all(s["selector"] in known for s in steps["steps"])
    # verification steps are not network mutations
    by_id = {s["id"]: s for s in steps["steps"]}
    assert by_id["render_gates"]["network_mutation"] is False
    assert by_id["lead_capture"]["network_mutation"] is False
    assert by_id["build_questions"]["network_mutation"] is True

    with pytest.raises(qb.QuizPlanInvalid):
        qb.build_step_plan(plan, {"anchors": [{"id": "quiz.list.add_survey"}], "version": "x"})


def test_survey_task_translation_keeps_every_question_and_branch(plan):
    p = qb.normalize_plan(plan)
    task = qb.to_survey_task(p)
    assert task["rail"] == "managed_browser"
    assert task["build_type"] == "marketing_quiz"
    assert len(task["survey_fields"]) == len(p["questions"])
    assert task["converge_slide"] == "Contact Capture"
    assert task["capture_consent"]["required"] is True
    assert task["capture_consent"]["text"] == p["capture"]["consent"]["text"]

    rules = task["conditional_logic"]
    assert len(rules) == 1
    assert rules[0]["if_field"] == "How do you get clients?"
    assert rules[0]["if_value"] == "Paid ads"
    assert rules[0]["then_slide"].startswith("Q4 ")


def test_dependency_plan_reuses_and_never_duplicates(plan):
    p = qb.normalize_plan(plan)
    fresh = qb.dependency_plan(p)
    keys = [f["field_key"] for f in fresh["custom_fields"]]
    assert len(keys) == len(set(keys))
    assert all(k.startswith("zhc_") for k in keys)
    assert {"zhc_quiz_outcome", "zhc_quiz_score", "zhc_quiz_consent"} <= set(keys)
    assert all(f["action"] == "create" for f in fresh["custom_fields"])
    assert all(t["action"] == "create" for t in fresh["tags"])

    reused = qb.dependency_plan(
        p, existing_field_keys=["ZHC_QUIZ_OUTCOME", "zhc_quiz_email"],
        existing_tags=["zhc_quiz_lead"])
    actions = {f["field_key"]: f["action"] for f in reused["custom_fields"]}
    assert actions["zhc_quiz_outcome"] == "reuse"
    assert actions["zhc_quiz_email"] == "reuse"
    assert actions["zhc_quiz_score"] == "create"
    assert {t["tag"]: t["action"] for t in reused["tags"]}["zhc_quiz_lead"] == "reuse"
    assert reused["tag_attachment"]["method"] == "workflow"


def test_dry_run_never_touches_a_browser(plan):
    built = qb.build_quiz(plan, "/nonexistent-evidence-root", dry_run=True)
    assert built["status"] == "PLANNED"
    assert built["build_result"] is None
    assert built["delegated_builder"] == "ghl_survey_builder.build_survey"


# ---------------------------------------------------------------------------
# CP01 frozen interface
# ---------------------------------------------------------------------------
def test_cp01_interface_is_frozen(plan, fixture):
    committed = load(CP01_PATH)
    regenerated = qb.cp01_record(plan, fixture, fixture_path=str(FIXTURE_PATH))

    assert committed["checkpoint_id"] == "WF34-CP01"
    assert committed["workflow_id"] == "WF34"
    assert committed["plan_schema"] == regenerated["plan_schema"]
    assert committed["fixture_schema"] == regenerated["fixture_schema"]
    assert committed["score_band"] == regenerated["score_band"] == {"min": 0, "max": 11}
    assert committed["outcome_mapping"] == regenerated["outcome_mapping"]
    assert committed["boundary_answers"] == regenerated["boundary_answers"]
    assert committed["capture_policy"] == regenerated["capture_policy"]
    assert committed["dependent_fields"]["custom_fields"] == \
        regenerated["dependent_fields"]["custom_fields"]
    assert committed["fixture_sha256"] == regenerated["fixture_sha256"]
    assert committed["course_quiz_substitution"] == "refused"
    assert set(committed["consumers"]) == {"WF07", "WF09", "WF22", "WF23"}


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------
def test_module_selftest_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-I", str(_TOOLS_DIR / "ghl_marketing_quiz_builder.py"), "--selftest"],
        capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[selftest] PASS" in proc.stdout
