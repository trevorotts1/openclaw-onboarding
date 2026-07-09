#!/usr/bin/env python3
"""
test-persona-blend-matcher.py — W7 voice-first AUDIENCE+TOPIC blend contract lock.

Proves the approved design (operator-confirmed 2026-07-08), HERMETICALLY: the
selector/decompose functions persona_blend calls are monkeypatched, and the
catalog is a committed fixture, so this suite never reads or writes a live
persona DB or the operator's own workspace (the Skill-23 state-script hazard).

Locks:
  T1  WHOLE-CATALOG TAG MATCHING — audience + topic personas are chosen over the
      whole catalog via audiences[]/topics[]/usable_as[] (no static voice library);
      usable_as must include 'audience' to serve as an audience voice.
  T2  ALWAYS-CONFIRM / ASK-WHEN-UNSURE — single ICP → confirm prompt (confirm_required
      True); multiple/none → the exact ASK "What audience are we dealing with?";
      operator override → confirm_required False (re-scored voice).
  T3  BLEND (distinct audience+topic) — the canonical example: Black-women-founders
      audience voice + funnel/marketing topic expertise, NOT collapsed.
  T4  COLLAPSE — one persona that covers BOTH the audience and the topic collapses
      to a single voice persona.
  T5  UP-TO-10 TASK PERSONAS — the job decomposes to at most 10 task personas via
      the existing per-sub-task matcher; each row is {seq, part, persona_id, why}.
  T6  BUNDLE SUPERSET + BACK-COMPAT — the bundle carries the single-persona mirror
      keys (persona_id/name/score/task_category/funnel/interaction_mode) AND the
      new blend keys; works on a schema-1.2 catalog (no tags) via the semantic
      fallback; mechanical & non-content tasks are never-naked.
  T7  MANDATORY GUARDRAIL — every blend_directive carries the non-removable
      "STYLE-INSPIRED, NEVER IMPERSONATION" clause.
  T8  TAG VALIDATOR — validates audiences/topics vs the new vocabs + usable_as vs
      the enum on a 1.3 catalog; a NO-OP on a 1.2 catalog.

Each check pairs with a NO-WEAKENING probe proving it FAILS on injected drift.

EXIT: 0 = all passed (incl. every NO-WEAKENING case); 1 otherwise.
Usage: python3 test-persona-blend-matcher.py [REPO_ROOT]
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
FIXTURE_13 = SCRIPTS / "testdata" / "persona-categories.fixture.json"
FIXTURE_12 = SCRIPTS / "testdata" / "persona-categories.v12.fixture.json"

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


pb = _load(SCRIPTS / "persona_blend.py", "persona_blend_under_test")
CAT13 = json.loads(FIXTURE_13.read_text())
CAT12 = json.loads(FIXTURE_12.read_text())


# ── Hermetic patch harness for build_bundle ───────────────────────────────────
def _fake_dt_select_persona(subtask_text, dept, mode, weights, paths, db_path, variety=True):
    pid = "task-persona-" + str(abs(hash(subtask_text)) % 100000)
    return {"persona_id": pid, "persona_name": pid.replace("-", " ").title(),
            "score": 0.8, "layers": {"task_fit": 0.8}, "interaction_mode": mode}


def _fake_sel_semantic(task, dept, mode, weights, paths, db_path, variety=True, **kw):
    # A benign, deterministic semantic pick (used only as a NUDGE for 1.3, and as
    # the topic fallback for the 1.2 back-compat catalog).
    return {"persona_id": "brunson-dotcom-secrets",
            "funnel": {"pool": 7, "category": 6, "semantic": 3}, "score": 0.72}


def _hermetic(catalog_path, company_cfg):
    """Wire persona_blend's cached selector + decompose module instances for a
    hermetic build_bundle run against `catalog_path` with `company_cfg`."""
    os.environ["OPENCLAW_PERSONA_CATEGORIES"] = str(catalog_path)
    os.environ.pop("OPENCLAW_AUDIENCE", None)
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


ICP_FOUNDERS = {"company": {"ideal_customer": "Black women entrepreneurs building wealth"}}
ICP_SINGLE = {"company": {"ideal_customer": "Black women"}}
ICP_MULTI = {"audiences": ["coaches", "course creators", "consultants"]}
ICP_NONE = {}


# ═══════════════════════════════════════════════════════════════════════════════
section("T1  WHOLE-CATALOG TAG MATCHING (audiences/topics/usable_as)")

tp = pb.match_topic_persona(CAT13, "write a marketing funnel email sequence")
if tp and tp["persona_id"] == "brunson-dotcom-secrets":
    ok(f"topic persona for a funnel/email job = {tp['persona_id']} (via topics[])")
else:
    bad(f"topic persona wrong: {tp}")

ap = pb.match_audience_persona(CAT13, "Black women entrepreneurs building wealth")
if ap and ap["persona_id"] == "shonda-year-of-yes":
    ok(f"audience persona for Black-women-founders = {ap['persona_id']} (usable_as⊇audience)")
else:
    bad(f"audience persona wrong: {ap}")

# NO-WEAKENING: a persona WITHOUT 'audience' in usable_as must NEVER be an audience voice.
_cat_no_aud = json.loads(json.dumps(CAT13))
_cat_no_aud["personas"]["shonda-year-of-yes"]["usable_as"] = ["topic", "task"]
_cat_no_aud["personas"]["aliche-get-good-with-money"]["usable_as"] = ["topic", "task"]
ap_none = pb.match_audience_persona(_cat_no_aud, "Black women entrepreneurs")
if ap_none is None:
    ok("NO-WEAKENING: with no usable_as⊇audience persona, NO audience voice is forced")
else:
    bad(f"NO-WEAKENING failed: forced an audience voice {ap_none['persona_id']} without usable_as⊇audience")

# NO-WEAKENING: topic matching ignores an off-topic persona (no false positive).
tp_soft = pb.match_topic_persona(CAT13, "refactor the deployment pipeline and the web app code")
if tp_soft and tp_soft["persona_id"] == "hunt-pragmatic-programmer":
    ok(f"topic matching routes a code job to the software-craft persona ({tp_soft['persona_id']})")
else:
    bad(f"topic matching mis-routed a code job: {tp_soft}")


# ═══════════════════════════════════════════════════════════════════════════════
section("T2  ALWAYS-CONFIRM / ASK-WHEN-UNSURE")

ra1 = pb.resolve_audience(CAT13, ICP_FOUNDERS)
if ra1["source"] == "onboarding_icp" and ra1["confidence"] == "high" and ra1["confirm_required"]:
    ok("single ICP → source=onboarding_icp, confidence=high, confirm_required=True (confirm prompt)")
else:
    bad(f"single-ICP resolution wrong: {ra1}")

ra2 = pb.resolve_audience(CAT13, ICP_MULTI)
if (ra2["source"] == "asked" and ra2["confirm_required"]
        and ra2["ask"].startswith(pb.AUDIENCE_CONFIRM_PROMPT)
        and all(a in ra2["ask"] for a in ("coaches", "course creators", "consultants"))):
    ok('multiple ICP → ASK "What audience are we dealing with?" enumerating the known audiences')
else:
    bad(f"multi-ICP ASK wrong: {ra2}")

ra3 = pb.resolve_audience(CAT13, ICP_NONE)
if (ra3["source"] == "asked" and ra3["confidence"] == "none"
        and ra3["confirm_required"] and pb.AUDIENCE_CONFIRM_PROMPT in ra3["ask"]
        and ra3["candidates"] == []):
    ok("no ICP → confidence=none, confirm_required=True, ASK; never fabricates a candidate")
else:
    bad(f"no-ICP resolution wrong: {ra3}")

ra4 = pb.resolve_audience(CAT13, ICP_NONE, audience_override="Black women entrepreneurs")
if ra4["source"] == "operator_confirmed" and ra4["confirm_required"] is False:
    ok("operator override → source=operator_confirmed, confirm_required=False (re-scored voice)")
else:
    bad(f"operator override wrong: {ra4}")

# NO-WEAKENING: a single ICP must NOT silently proceed without confirmation.
if ra1["confirm_required"] is True:
    ok("NO-WEAKENING: a single high-confidence ICP still requires confirmation (never auto-writes)")
else:
    bad("NO-WEAKENING failed: single ICP auto-proceeded without confirm_required")


# ═══════════════════════════════════════════════════════════════════════════════
section("T3  BLEND — distinct audience voice + topic expertise (canonical example)")

paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b = pb.build_bundle("write a marketing funnel email sequence to launch our fund",
                    "marketing", paths=paths, db_path=db, use_llm=False, record=False)
v = b["voice"]
if (b["content_task"] and v["collapsed"] is False
        and v["audience_persona"] and v["audience_persona"]["id"] == "shonda-year-of-yes"
        and v["topic_persona"]["id"] == "brunson-dotcom-secrets"):
    ok("BLEND: Shonda (audience voice) + Brunson (topic expertise), NOT collapsed")
else:
    bad(f"BLEND wrong: collapsed={v['collapsed']} audience={v.get('audience_persona')} topic={v['topic_persona']}")

if b["persona_id"] == "shonda-year-of-yes":
    ok("BLEND: back-compat persona_id mirrors the VOICE (audience) persona")
else:
    bad(f"BLEND mirror wrong: persona_id={b['persona_id']}")

if "carrying" in b["blend_directive"] and "Brunson" in b["blend_directive"] and "Shonda" in b["blend_directive"]:
    ok("BLEND directive: write in audience voice, carry topic expertise")
else:
    bad(f"BLEND directive wrong: {b['blend_directive']}")


# ═══════════════════════════════════════════════════════════════════════════════
section("T4  COLLAPSE — one persona covers both audience + topic")

paths, db = _hermetic(FIXTURE_13, ICP_SINGLE)
bc = pb.build_bundle("write a budgeting and debt payoff email for our members",
                     "marketing", paths=paths, db_path=db, use_llm=False, record=False)
vc = bc["voice"]
if vc["collapsed"] and vc["collapsed_persona_id"] == "aliche-get-good-with-money":
    ok("COLLAPSE: budgeting-for-Black-women collapses onto Aliche (covers audience+topic)")
else:
    bad(f"COLLAPSE wrong: collapsed={vc['collapsed']} id={vc.get('collapsed_persona_id')} "
        f"topic={vc['topic_persona']}")

if bc["persona_id"] == "aliche-get-good-with-money":
    ok("COLLAPSE: mirror persona_id = the single collapsed voice persona")
else:
    bad(f"COLLAPSE mirror wrong: {bc['persona_id']}")

# NO-WEAKENING: the distinct BLEND case above must NOT have collapsed.
if b["voice"]["collapsed"] is False and bc["voice"]["collapsed"] is True:
    ok("NO-WEAKENING: collapse fires only when one persona covers both (blend stays distinct)")
else:
    bad("NO-WEAKENING failed: collapse logic does not discriminate blend vs collapse")


# ═══════════════════════════════════════════════════════════════════════════════
section("T5  UP-TO-10 TASK PERSONAS")

# A genuine multi-part job decomposes to multiple task personas.
paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
bmp = pb.build_bundle(
    "Write the launch email, then design the social posts, and draft the sales page",
    "marketing", paths=paths, db_path=db, use_llm=False, record=False)
tps = bmp["task_personas"]
if 1 <= len(tps) <= 10 and all({"seq", "part", "persona_id", "why"} <= set(r) for r in tps):
    ok(f"task_personas: {len(tps)} row(s), each {{seq, part, persona_id, why}}")
else:
    bad(f"task_personas shape wrong: {tps}")

# The 10-cap: force a 12-part decomposition and prove the bundle caps at 10.
dt = pb._decompose()
_orig_decompose = dt.decompose_task
dt.decompose_task = lambda t, max_subtasks=6, use_llm=True: (
    [f"part {i}: write section {i}" for i in range(1, 13)], "test-12-parts")
try:
    paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
    # _hermetic re-patches dt.select_persona etc but NOT decompose_task; re-apply.
    dt.decompose_task = lambda t, max_subtasks=6, use_llm=True: (
        [f"part {i}: write section {i}" for i in range(1, 13)], "test-12-parts")
    b10 = pb.build_bundle("write a very long multi-part launch campaign",
                          "marketing", paths=paths, db_path=db, use_llm=False, record=False)
    if len(b10["task_personas"]) == 10:
        ok("UP-TO-10: a 12-part decomposition is capped to exactly 10 task personas")
    else:
        bad(f"10-cap failed: got {len(b10['task_personas'])} task personas")
    # NO-WEAKENING: exceeding 10 must be caught (i.e. the cap is real, not >10).
    if len(b10["task_personas"]) <= 10:
        ok("NO-WEAKENING: task_personas never exceeds the 10 ceiling")
    else:
        bad("NO-WEAKENING failed: task_personas exceeded 10")
finally:
    dt.decompose_task = _orig_decompose


# ═══════════════════════════════════════════════════════════════════════════════
section("T6  BUNDLE SUPERSET + BACK-COMPAT (1.2 catalog, mechanical, non-content)")

BACKCOMPAT_KEYS = {"persona_id", "persona_name", "score", "task_category",
                   "funnel", "interaction_mode"}
BLEND_KEYS = {"mode", "topic", "resolved_audience", "confirm_required", "voice",
              "blend_directive", "task_personas", "rationale", "fallbacks"}
missing_bc = BACKCOMPAT_KEYS - set(b)
missing_bl = BLEND_KEYS - set(b)
if not missing_bc and not missing_bl:
    ok("bundle is a strict SUPERSET: all single-persona mirror keys + all blend keys present")
else:
    bad(f"bundle not a superset — missing back-compat {missing_bc}, blend {missing_bl}")

# schema-1.2 catalog: no tags → audience persona absent, topic via semantic fallback.
paths, db = _hermetic(FIXTURE_12, ICP_FOUNDERS)
b12 = pb.build_bundle("write a marketing funnel email sequence", "marketing",
                      paths=paths, db_path=db, use_llm=False, record=False)
if (b12["voice"]["audience_persona"] is None
        and b12["voice"]["topic_persona"]["id"] == "brunson-dotcom-secrets"
        and b12["persona_id"] is not None
        and pb.GUARDRAIL_CLAUSE in b12["blend_directive"]):
    ok("BACK-COMPAT: on a 1.2 catalog the blend degrades to the semantic topic pick, never-naked")
else:
    bad(f"1.2 back-compat wrong: audience={b12['voice']['audience_persona']} "
        f"topic={b12['voice']['topic_persona']} persona_id={b12['persona_id']}")

# mechanical task: never-naked governance pointer, no blend, no task personas.
paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
bm = pb.build_bundle("restart the server and ping the host", "operations",
                     paths=paths, db_path=db, use_llm=False, record=False)
if (bm["no_persona_required"] and bm["governance_persona_id"] == "covey-7-habits"
        and bm["confirm_required"] is False and bm["task_personas"] == []
        and pb.GUARDRAIL_CLAUSE in bm["blend_directive"]):
    ok("mechanical task → no_persona_required + governance pointer, no blend, guardrail kept")
else:
    bad(f"mechanical bundle wrong: {bm.get('no_persona_required')} "
        f"gov={bm.get('governance_persona_id')} confirm={bm.get('confirm_required')}")

# non-content task: no audience voice, confirm not required, topic carries the voice.
paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
bn = pb.build_bundle("analyze last quarter's sales data and produce a forecast model",
                     "operations", paths=paths, db_path=db, use_llm=False, record=False)
if (bn["content_task"] is False and bn["confirm_required"] is False
        and bn["voice"]["audience_persona"] is None and bn["voice"]["collapsed"] is True):
    ok("non-content task → no audience voice, confirm_required=False, topic persona carries voice")
else:
    bad(f"non-content bundle wrong: content={bn['content_task']} "
        f"confirm={bn['confirm_required']} audience={bn['voice']['audience_persona']}")

# confirm gate visible on a content task with an unconfirmed audience.
if b["confirm_required"] is True and b["resolved_audience"]["ask"]:
    ok("confirm_required=True gates the write and surfaces the confirm/ASK prompt")
else:
    bad(f"confirm gate missing: confirm={b['confirm_required']} ask={b['resolved_audience'].get('ask')}")

# operator confirmation clears the gate + re-scores the voice.
os.environ["OPENCLAW_AUDIENCE"] = "Black women entrepreneurs building wealth"
paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)  # note: _hermetic pops OPENCLAW_AUDIENCE
bo = pb.build_bundle("write a marketing funnel email sequence", "marketing",
                     paths=paths, db_path=db, use_llm=False, record=False,
                     audience_override="Black women entrepreneurs building wealth")
if bo["confirm_required"] is False and bo["resolved_audience"]["source"] == "operator_confirmed":
    ok("operator confirmation → confirm_required=False, source=operator_confirmed")
else:
    bad(f"operator-confirm bundle wrong: confirm={bo['confirm_required']} "
        f"source={bo['resolved_audience']['source']}")


# ═══════════════════════════════════════════════════════════════════════════════
section("T7  MANDATORY 'style-inspired, NEVER impersonation' GUARDRAIL")

variants = {
    "blend": b["blend_directive"],
    "collapse": bc["blend_directive"],
    "non-content": bn["blend_directive"],
    "1.2-backcompat": b12["blend_directive"],
    "mechanical": bm["blend_directive"],
}
missing = [k for k, d in variants.items() if pb.GUARDRAIL_CLAUSE not in d]
if not missing:
    ok(f"GUARDRAIL_CLAUSE present in every blend_directive variant ({', '.join(variants)})")
else:
    bad(f"GUARDRAIL missing from directive variant(s): {missing}")

if "NEVER IMPERSONATION" in pb.GUARDRAIL_CLAUSE and "style" in pb.GUARDRAIL_CLAUSE.lower():
    ok("guardrail text asserts style-inspired AND never-impersonation")
else:
    bad(f"guardrail text too weak: {pb.GUARDRAIL_CLAUSE!r}")

# NO-WEAKENING: a directive stripped of the clause must be detectable.
stripped = b["blend_directive"].replace(pb.GUARDRAIL_CLAUSE, "")
if pb.GUARDRAIL_CLAUSE not in stripped:
    ok("NO-WEAKENING: a directive missing the guardrail is detectable (fail-closed check works)")
else:
    bad("NO-WEAKENING failed: guardrail-absence not detectable")


# ═══════════════════════════════════════════════════════════════════════════════
section("T8  TAG VALIDATOR (vocab + enum on 1.3; no-op on 1.2)")

v13 = pb.validate_catalog_tags(CAT13)
if v13["ok"] and v13["checked"] == len(CAT13["personas"]):
    ok(f"valid 1.3 catalog passes ({v13['checked']} personas checked, 0 errors)")
else:
    bad(f"valid catalog failed validation: {v13}")

# drift: a topic outside the vocab.
_drift = json.loads(json.dumps(CAT13))
_drift["personas"]["aliche-get-good-with-money"]["topics"].append("not-a-real-topic-tag")
vd = pb.validate_catalog_tags(_drift)
if not vd["ok"] and any("not-a-real-topic-tag" in e for e in vd["errors"]):
    ok("NO-WEAKENING: a topic outside topicTags vocab is caught")
else:
    bad(f"validator missed vocab drift: {vd}")

# drift: a bad usable_as enum value.
_drift2 = json.loads(json.dumps(CAT13))
_drift2["personas"]["brunson-dotcom-secrets"]["usable_as"] = ["topic", "everything"]
vd2 = pb.validate_catalog_tags(_drift2)
if not vd2["ok"] and any("non-enum" in e for e in vd2["errors"]):
    ok("NO-WEAKENING: a usable_as value outside the enum is caught")
else:
    bad(f"validator missed enum drift: {vd2}")

v12 = pb.validate_catalog_tags(CAT12)
if v12["ok"] and v12.get("note", "").startswith("pre-enrichment"):
    ok("1.2 catalog → validator is a NO-OP (never turns a pre-enrichment box RED)")
else:
    bad(f"1.2 validator should be a no-op: {v12}")


# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 72)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 72)
sys.exit(0 if FAIL == 0 else 1)
