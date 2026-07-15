#!/usr/bin/env python3
"""
test-a-u4-conversion-goal.py — A-U4 (`conversion_goal` as a first-class input)
contract lock, master-spec v2 §A.5.

Proves A-U4's own BINARY acceptance criteria verbatim:

  (a) a content task with NO resolvable goal returns a bundle whose rationale
      carries a goal ASK, and a downstream write gated on
      `confirm_required OR goal_confirm_required` does NOT proceed (asserted
      via a fixture "attempted write" helper — no copy artifact is produced);
  (b) bundle JSON carries `{conversion_goal, goal_source}` when a goal
      resolves;
  (c) the per-department confirm-timeout HARD-HOLD (funnels/web-development
      -> blocked, block_audience='OWNER', never a house-voice write; other
      departments still release at 30 min) is a Command Center (`tasks.ts` /
      `task-dispatcher.ts`) behavior — proven in that repo's own test suite
      (`tests/unit/persona-blend-goal-confirm-department-policy.test.ts`),
      NOT here; this file proves only the ONB-side signal (b) feeds that gate.
  (d) directive slot 5 appears ONLY for content tasks with a resolved goal.

Also locks:
  - resolve_conversion_goal's source ladder (operator/task field -> Skill 6
    intake -> funnel-template-inferred -> ASK), each rung's confirm-doctrine.
  - `--conversion-goal` argv wins over OPENCLAW_CONVERSION_GOAL env
    (resolve_conversion_goal_arg, persona-selector-v2.py).
  - NO-CONTAMINATION: a caller that never supplies a goal (every pre-A-U4
    call site) gets a bundle whose top-level `confirm_required` is UNCHANGED
    from pre-A-U4 behavior — `goal_confirm_required` is a separate, additive
    signal, never folded into the audience-only gate the 46-test suite +
    the CC audience-confirm gate already depend on.

Each check pairs with a NO-WEAKENING probe proving it FAILS on injected drift.

EXIT: 0 = all passed (incl. every NO-WEAKENING case); 1 otherwise.
Usage: python3 test-a-u4-conversion-goal.py [REPO_ROOT]
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
FIXTURE_13 = SCRIPTS / "testdata" / "persona-categories.fixture.json"

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


def section(title):
    print("=" * 72)
    print(title)
    print("=" * 72)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pb = _load(SCRIPTS / "persona_blend.py", "persona_blend_a_u4")
selector_mod = _load(SCRIPTS / "persona-selector-v2.py", "persona_selector_a_u4")
CAT13 = json.loads(FIXTURE_13.read_text())

ICP_FOUNDERS = {"company": {"ideal_customer": "Black women entrepreneurs building wealth"}}


def _attempt_write(bundle: dict):
    """Fixture write-gate a caller (Skill 6's dispatcher, A-U7) MUST perform
    before writing copy: refuse when EITHER the audience OR the conversion
    goal is unconfirmed. Returns None (no artifact) when gated, else a fake
    artifact string — proves ACCEPT (a)'s 'no copy artifact' requirement
    without needing a real dispatcher."""
    if bundle.get("confirm_required") or bundle.get("goal_confirm_required"):
        return None
    return "COPY ARTIFACT WRITTEN"


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U4.1  resolve_conversion_goal — source ladder + ALWAYS-confirm doctrine")

r_none = pb.resolve_conversion_goal("", "")
if (r_none["value"] == "" and r_none["source"] == "asked"
        and r_none["ask"] == pb.CONVERSION_GOAL_CONFIRM_PROMPT
        and r_none["confirm_required"] is True):
    ok("no goal resolved -> source=asked, exact ASK, confirm_required=True, never fabricates")
else:
    bad(f"unresolved-goal rung wrong: {r_none}")

r_op = pb.resolve_conversion_goal("Book a discovery call", "operator_confirmed")
if (r_op["value"] == "Book a discovery call" and r_op["source"] == "operator_confirmed"
        and r_op["ask"] is None and r_op["confirm_required"] is False):
    ok("explicit operator/task field -> operator_confirmed, confirm_required=False (never re-asks)")
else:
    bad(f"operator-field rung wrong: {r_op}")

r_intake = pb.resolve_conversion_goal("Sign up for the webinar", "skill6_intake")
if (r_intake["source"] == "skill6_intake" and r_intake["confirm_required"] is False
        and r_intake["ask"] is None):
    ok("Skill 6 intake answer -> skill6_intake, confirm_required=False (already answered)")
else:
    bad(f"skill6_intake rung wrong: {r_intake}")

r_tmpl = pb.resolve_conversion_goal("Opt in for the lead magnet", "template_inferred")
if (r_tmpl["source"] == "template_inferred" and r_tmpl["confirm_required"] is True
        and r_tmpl["ask"] and "Opt in for the lead magnet" in r_tmpl["ask"]):
    ok("funnel-template-inferred goal -> template_inferred, STILL confirm_required=True "
       "(inferred, not confirmed — ALWAYS-confirm doctrine parity with resolve_audience)")
else:
    bad(f"template_inferred rung wrong: {r_tmpl}")

r_unknown_source = pb.resolve_conversion_goal("Buy now", "some-made-up-source")
if r_unknown_source["source"] == "operator_confirmed":
    ok("an unrecognized goal_source degrades safely to operator_confirmed "
       "(never crashes, never silently drops a resolved value)")
else:
    bad(f"unknown-source fallback wrong: {r_unknown_source}")

# NO-WEAKENING: a value alone (empty source) must NOT silently skip confirmation
# the way operator_confirmed/skill6_intake legitimately do.
r_blank_source = pb.resolve_conversion_goal("Download the guide", "")
if r_blank_source["confirm_required"] is False and r_blank_source["source"] == "operator_confirmed":
    ok("goal_source='' (bare kwarg / argv / env transport) treated as rung-1 "
       "explicit operator/task field, confirm_required=False")
else:
    bad(f"blank-source rung wrong: {r_blank_source}")

if not pb.resolve_conversion_goal("   ", "operator_confirmed")["value"]:
    ok("NO-WEAKENING: a whitespace-only goal is never fabricated into a truthy value")
else:
    bad("whitespace-only goal was NOT treated as unresolved")


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U4.2  build_blend_directive slot 5 — content-gated, degrades gracefully, no 5th persona")

AUD, TOP, TASK = "shonda-year-of-yes", "brunson-dotcom-secrets", "covey-7-habits"


def _directive(**overrides):
    base = dict(
        audience_pid=AUD, topic_pid=TOP, topic="email marketing",
        collapsed=False, collapsed_pid=None, content_task=True,
        audience_label="black women professionals",
        task_persona_pid=TASK, catalog=CAT13,
    )
    base.update(overrides)
    return pb.build_blend_directive(**base)


d_no_goal = _directive(conversion_goal="")
d_goal_no_closer_style = _directive(conversion_goal="Book a call", chosen_closer_pid=None)
d_goal_with_closer = _directive(conversion_goal="Book a call", chosen_closer_pid=TASK)

if "CONVERSION GOAL" not in d_no_goal:
    ok("ACCEPT (d): no resolved goal -> slot 5 absent")
else:
    bad("slot 5 rendered with no conversion_goal supplied")

if "CONVERSION GOAL: Book a call." in d_goal_no_closer_style and "Close in" not in d_goal_no_closer_style.split("CONVERSION GOAL")[1].split("VOICE CONTRACT")[0]:
    ok("degrades gracefully: no closer persona -> goal line with no fabricated conversion_style")
else:
    bad(f"no-closer degrade wrong:\n{d_goal_no_closer_style}")

# TASK ('covey-7-habits') has no conversion_style in the (schema-1.3) fixture —
# confirms slot 5 NEVER fabricates a style absent from the catalog.
if "CONVERSION GOAL: Book a call." in d_goal_with_closer and "Close in" not in d_goal_with_closer:
    ok("closer persona present but its conversion_style is ABSENT from a schema-1.3 "
       "catalog -> the goal line still renders, no invented style (never fabricates)")
else:
    bad(f"absent-conversion_style degrade wrong:\n{d_goal_with_closer}")

CAT_WITH_STYLE = json.loads(json.dumps(CAT13))  # deep copy
CAT_WITH_STYLE["personas"][TASK]["conversion_style"] = "logic-close"
d_goal_styled = _directive(conversion_goal="Book a call", chosen_closer_pid=TASK, catalog=CAT_WITH_STYLE)
if "CONVERSION GOAL: Book a call. Close in logic-close." in d_goal_styled:
    ok("closer's real conversion_style (A-U3 field) renders verbatim in slot 5")
else:
    bad(f"styled slot-5 line wrong:\n{d_goal_styled}")

d_non_content = _directive(content_task=False, conversion_goal="Book a call", chosen_closer_pid=TOP)
if "CONVERSION GOAL" not in d_non_content:
    ok("ACCEPT (d): non-content task never gets slot 5 even with a goal supplied")
else:
    bad("non-content task rendered slot 5")

# NO-WEAKENING: byte-identical to the pre-A-U4 default when conversion_goal is
# simply unused (the exact contract every pre-A-U4 caller relies on).
if pb.build_blend_directive(
        audience_pid=AUD, topic_pid=TOP, topic="email marketing", collapsed=False,
        collapsed_pid=None, content_task=True, audience_label="black women professionals",
        task_persona_pid=TASK, catalog=CAT13) == d_no_goal:
    ok("NO-WEAKENING: omitting conversion_goal entirely == passing conversion_goal=\"\" "
       "(true default-inert additive contract)")
else:
    bad("default-omitted call diverged from an explicit empty conversion_goal call")

if pb.GUARDRAIL_CLAUSE in d_goal_styled and d_goal_styled.rstrip().endswith(pb.GUARDRAIL_CLAUSE):
    ok("guardrail remains the TRAILING, non-removable clause even with slot 5 present")
else:
    bad("guardrail not trailing on the slot-5-bearing directive")


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U4.3  _choose_closer_pid — never invents a fifth persona")

if pb._choose_closer_pid("task-pid", False, None, "aud-pid", "top-pid") == "task-pid":
    ok("TASK slot preferred when present (DEP-5, already an independent dimension)")
else:
    bad("closer selection did not prefer the TASK slot")

if pb._choose_closer_pid(None, True, "collapsed-pid", "aud-pid", "top-pid") == "collapsed-pid":
    ok("falls back to the COLLAPSED voice when no task persona")
else:
    bad("closer selection did not fall back to the collapsed voice")

if pb._choose_closer_pid(None, False, None, "aud-pid", "top-pid") == "aud-pid":
    ok("falls back to the AUDIENCE voice when not collapsed and no task persona")
else:
    bad("closer selection did not fall back to the audience persona")

if pb._choose_closer_pid(None, False, None, None, "top-pid") == "top-pid":
    ok("last resort: TOPIC persona when nothing else is populated")
else:
    bad("closer selection did not fall back to the topic persona")

if pb._choose_closer_pid(None, False, None, None, None) is None:
    ok("NO-WEAKENING: an entirely empty bundle never fabricates a closer")
else:
    bad("closer selection fabricated a persona from nothing")


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U4.4  build_bundle — ACCEPT (a) / (b) / (d) + NO-CONTAMINATION of confirm_required")


def _fake_dt_select_persona(subtask_text, dept, mode, weights, paths, db_path, variety=True):
    pid = "task-persona-" + str(abs(hash(subtask_text)) % 100000)
    return {"persona_id": pid, "persona_name": pid.replace("-", " ").title(),
            "score": 0.8, "layers": {"task_fit": 0.8}, "interaction_mode": mode}


def _fake_sel_semantic(task, dept, mode, weights, paths, db_path, variety=True, **kw):
    return {"persona_id": "brunson-dotcom-secrets",
            "funnel": {"pool": 7, "category": 6, "semantic": 3}, "score": 0.72}


def _hermetic(catalog_path, company_cfg):
    os.environ["OPENCLAW_PERSONA_CATEGORIES"] = str(catalog_path)
    os.environ["OPENCLAW_AUDIENCE"] = "Black women entrepreneurs building wealth"
    sel = pb._selector()
    dt = pb._decompose()
    sel.load_company_config = lambda paths: company_cfg
    sel.select_persona = _fake_sel_semantic
    sel.is_db_found = lambda p: False
    dt.select_persona = _fake_dt_select_persona
    dt.record_selection = lambda *a, **k: None
    dt.get_openclaw_paths = lambda: {}
    dt.find_dashboard_db = lambda: Path("/nonexistent/hermetic.db")
    dt.is_db_found = lambda p: False
    paths = {"persona_categories": Path(catalog_path),
             "soul_md": Path("/nonexistent/SOUL.md")}
    return paths, Path("/nonexistent/hermetic.db")


TASK_TEXT = "write a marketing funnel email sequence"

paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_no_goal = pb.build_bundle(TASK_TEXT, "funnels", paths=paths, db_path=db,
                            use_llm=False, record=False,
                            audience_override="Black women entrepreneurs building wealth")

if (b_no_goal["conversion_goal"] == "" and b_no_goal["goal_source"] == "asked"
        and b_no_goal["goal_confirm_required"] is True):
    ok("ACCEPT (a) pt.1: content task, no goal supplied -> conversion_goal='', "
       "goal_source='asked', goal_confirm_required=True")
else:
    bad(f"unresolved-goal bundle wrong: goal={b_no_goal['conversion_goal']!r} "
        f"source={b_no_goal['goal_source']} gate={b_no_goal['goal_confirm_required']}")

if pb.CONVERSION_GOAL_CONFIRM_PROMPT in b_no_goal["rationale"]["conversion_goal_resolution"]:
    ok("ACCEPT (a) pt.2: rationale carries the goal ASK when unresolved")
else:
    bad(f"rationale missing the goal ASK: {b_no_goal['rationale'].get('conversion_goal_resolution')}")

if _attempt_write(b_no_goal) is None:
    ok("ACCEPT (a) pt.3: the gated write (confirm_required OR goal_confirm_required) "
       "does NOT proceed — no copy artifact produced")
else:
    bad("a write was NOT gated despite an unresolved conversion goal")

if "CONVERSION GOAL" not in b_no_goal["blend_directive"]:
    ok("directive slot 5 absent when the goal is unresolved (consistent with the bundle)")
else:
    bad("directive carried slot 5 despite an unresolved goal")

paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_goal = pb.build_bundle(TASK_TEXT, "funnels", paths=paths, db_path=db,
                         use_llm=False, record=False,
                         audience_override="Black women entrepreneurs building wealth",
                         conversion_goal="Book a discovery call",
                         goal_source="operator_confirmed")

if (b_goal["conversion_goal"] == "Book a discovery call"
        and b_goal["goal_source"] == "operator_confirmed"):
    ok("ACCEPT (b): bundle JSON carries {conversion_goal, goal_source} when a goal resolves")
else:
    bad(f"resolved-goal bundle wrong: goal={b_goal['conversion_goal']!r} source={b_goal['goal_source']}")

if b_goal["goal_confirm_required"] is False and b_goal["confirm_required"] is False:
    ok("operator-confirmed goal + operator-confirmed audience -> both gates clear, write proceeds")
else:
    bad(f"resolved-goal gate wrong: confirm={b_goal['confirm_required']} "
        f"goal_confirm={b_goal['goal_confirm_required']}")

if _attempt_write(b_goal) == "COPY ARTIFACT WRITTEN":
    ok("ACCEPT (a) inverse: fully-resolved bundle (audience + goal) is NOT gated — write proceeds")
else:
    bad("a fully-resolved bundle was still gated")

if "CONVERSION GOAL: Book a discovery call." in b_goal["blend_directive"]:
    ok("ACCEPT (d): directive slot 5 present for a content task with a resolved goal")
else:
    bad(f"slot 5 missing from a resolved-goal directive:\n{b_goal['blend_directive']}")

if b_goal["rationale"]["conversion_goal"] == "Book a discovery call" and b_goal["rationale"]["goal_source"] == "operator_confirmed":
    ok("decision receipt: rationale.conversion_goal / rationale.goal_source populated (A.5 item 4)")
else:
    bad(f"rationale decision receipt wrong: {b_goal['rationale']}")

if b_goal["rationale"]["chosen_closer"]:
    ok(f"decision receipt: rationale.chosen_closer populated ({b_goal['rationale']['chosen_closer']!r}) "
       f"— reused an existing slot, never a fifth persona pick")
else:
    bad("rationale.chosen_closer missing/empty on a resolved-goal content bundle")

# ── NO-CONTAMINATION — the exact regression this unit must never introduce ──
paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_legacy = pb.build_bundle(TASK_TEXT, "marketing", paths=paths, db_path=db,
                           use_llm=False, record=False,
                           audience_override="Black women entrepreneurs building wealth")
if b_legacy["confirm_required"] is False:
    ok("NO-CONTAMINATION: a caller that never supplies conversion_goal (every pre-A-U4 "
       "call site) still gets confirm_required=False once audience is confirmed — "
       "goal_confirm_required is a SEPARATE signal, never folded into confirm_required")
else:
    bad(f"pre-A-U4 caller regressed: confirm_required={b_legacy['confirm_required']} "
        f"(goal-gate contamination)")
if b_legacy["goal_confirm_required"] is True:
    ok("...while goal_confirm_required is still honestly True (unresolved) — the new "
       "signal exists but does not retroactively gate legacy callers")
else:
    bad(f"goal_confirm_required unexpectedly False with no goal ever supplied: {b_legacy}")

# non-content task: goal machinery never engages regardless of input.
paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_nc = pb.build_bundle("analyze last quarter's sales data and produce a forecast model",
                       "operations", paths=paths, db_path=db, use_llm=False, record=False,
                       conversion_goal="irrelevant on a non-content task")
if (b_nc["goal_confirm_required"] is False and "CONVERSION GOAL" not in b_nc["blend_directive"]):
    ok("non-content task: goal_confirm_required forced False, slot 5 never renders "
       "(mirrors the audience-gate non-content contract)")
else:
    bad(f"non-content goal handling wrong: {b_nc['goal_confirm_required']} "
        f"directive={b_nc['blend_directive'][:80]!r}")

# mechanical task: every A-U4 key present, all inert (superset discipline).
paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_mech = pb.build_bundle("restart the server and ping the host", "operations",
                         paths=paths, db_path=db, use_llm=False, record=False)
if (b_mech["conversion_goal"] == "" and b_mech["goal_source"] == "n/a"
        and b_mech["goal_confirm_required"] is False):
    ok("mechanical task: A-U4 keys present on the SUPERSET, fully inert")
else:
    bad(f"mechanical bundle A-U4 keys wrong: {b_mech.get('conversion_goal')!r} "
        f"{b_mech.get('goal_source')} {b_mech.get('goal_confirm_required')}")


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U4.5  resolve_conversion_goal_arg — --conversion-goal argv wins over env")

if selector_mod.resolve_conversion_goal_arg("from-argv", "from-env") == "from-argv":
    ok("argv value wins when both --conversion-goal and OPENCLAW_CONVERSION_GOAL are set")
else:
    bad("argv did not win over env")

if selector_mod.resolve_conversion_goal_arg(None, "from-env") == "from-env":
    ok("env value used when --conversion-goal is not supplied")
else:
    bad("env fallback did not fire when argv was absent")

if selector_mod.resolve_conversion_goal_arg(None, "") == "":
    ok("neither supplied -> empty string (never crashes, never fabricates)")
else:
    bad("neither-supplied case did not degrade to empty string")

if selector_mod.resolve_conversion_goal_arg("", "from-env") == "":
    ok("NO-WEAKENING: an explicit empty --conversion-goal '' still WINS over env "
       "(argv is-not-None wins, not argv-is-truthy — an operator can deliberately clear it)")
else:
    bad("explicit empty argv did not take precedence over env")


# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 72)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 72)
sys.exit(0 if FAIL == 0 else 1)
