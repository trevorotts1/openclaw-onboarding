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
  T9  CONTENT-INTENT IS WORD-WISE — ops tasks whose text merely CONTAINS a content
      substring ('ad' in read/download/admin, 'post' in compost, 'story' in
      history) stay non-content and never gate a write; genuine content still
      matches (whole-token/plural words + hyphenated/multi-word phrases).
  T10 TOPIC RATIONALE HONESTY — a pure semantic-nudge (no topics[] tag matched)
      defers so the emitted why never claims 'topics[] match the job on [] (0
      signal(s))'; a real hit still reports an accurate topics[] rationale.
  T11 MULTI-AUDIENCE (asked) — with several unconfirmed ICP audiences no voice is
      pre-committed (neutral directive, write still gated, ASK lists all); a single
      onboarding ICP is still pre-proposed for confirmation.
  T12 D8 — OPENCLAW_COMPANY_CONFIG ENV WIRING — detect_platform.get_openclaw_paths()
      honors the OPENCLAW_COMPANY_CONFIG override end-to-end, through the REAL
      (un-mocked) load_company_config() and resolve_audience(), so a client's
      onboarding ICP (company.ideal_customer) actually reaches the matcher; unset,
      it falls back to the company_dir-derived default with no stale leak.

Each check pairs with a NO-WEAKENING probe proving it FAILS on injected drift.
T12 is the one exception to the "everything mocked" header above — it loads a
FRESH, un-mocked persona-selector-v2.py module (never pb._selector()'s cache,
which T1-T11 monkeypatch load_company_config on) so the real detect_platform.py
env-var wiring is what's actually exercised, not a stand-in for it.

EXIT: 0 = all passed (incl. every NO-WEAKENING case); 1 otherwise.
Usage: python3 test-persona-blend-matcher.py [REPO_ROOT]
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
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
section("T9  CONTENT-INTENT is WORD-WISE — ops tasks with incidental substrings stay non-content")

# NO-WEAKENING: ops tasks whose text merely CONTAINS a content substring
# ('ad' in read/download/admin/grade/headshot, 'post' in compost, 'story' in
# history) must NOT be flagged as content — else the audience blend wrongly gates
# an ops write. Each of these returns True on the old substring test (the bug).
OPS_NON_CONTENT = [
    "read the logs and restart", "update the readme file", "download the report",
    "admin panel cleanup", "review the history of the directory",
    "compost the old branches", "grade the homework", "make a headshot thumbnail",
    "reconcile the admin ledger", "download the quarterly report",
]
_ops_wrong = [t for t in OPS_NON_CONTENT if pb.is_content_task(t) is not False]
if not _ops_wrong:
    ok(f"is_content_task=False for all {len(OPS_NON_CONTENT)} ops-with-incidental-substring tasks")
else:
    bad(f"is_content_task false-positives (should be non-content): {_ops_wrong}")

# The other half of the NO-WEAKENING pair: genuine content still matches (single
# words as whole tokens/plurals + hyphenated/multi-word phrases). Guards against
# over-correcting the fix into a regression on real content jobs.
GENUINE_CONTENT = [
    "write the launch email", "draft an Instagram carousel post",
    "record a podcast episode", "design the ad creative", "post to LinkedIn",
    "write the sales page copy", "design the posts", "send an e-mail blast",
    "build an opt-in page", "write an op-ed", "record a voiceover",
]
_content_wrong = [t for t in GENUINE_CONTENT if pb.is_content_task(t) is not True]
if not _content_wrong:
    ok(f"is_content_task=True for all {len(GENUINE_CONTENT)} genuine content tasks (no over-correction)")
else:
    bad(f"is_content_task missed genuine content: {_content_wrong}")

# Through the BUNDLE: a non-mechanical ops task must be content_task=False AND
# confirm_required=False (no audience voice, no write gate). This exact contract
# FAILS on the pre-fix code (content_task=True gated the write) and locks it.
for _optask in ("update the readme file", "reconcile the admin ledger",
                "download the quarterly report"):
    paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
    bo9 = pb.build_bundle(_optask, "operations", paths=paths, db_path=db,
                          use_llm=False, record=False)
    if (bo9["content_task"] is False and bo9["confirm_required"] is False
            and bo9["voice"]["audience_persona"] is None):
        ok(f"bundle: ops task {_optask!r} → content_task=False, confirm_required=False (no gate)")
    else:
        bad(f"bundle mis-gated ops task {_optask!r}: content={bo9['content_task']} "
            f"confirm={bo9['confirm_required']} audience={bo9['voice']['audience_persona']}")


# ═══════════════════════════════════════════════════════════════════════════════
section("T10  TOPIC RATIONALE HONESTY — never claim a topics[] match that did not happen")

# A pure semantic-NUDGE (no topics[] tag actually matched) must return None from
# match_topic_persona so the caller can emit an honest fallback rationale — never
# the misleading 'its topics[] match the job on [] (0 signal(s))'.
tp_nudge = pb.match_topic_persona(CAT13, "update the readme file",
                                  semantic_pick="brunson-dotcom-secrets")
if tp_nudge is None:
    ok("match_topic_persona returns None on a pure-nudge/no-topic-match job (defers to fallback)")
else:
    bad(f"pure-nudge did not defer: {tp_nudge}")

# A REAL topic hit still returns the persona with an accurate 'its topics[] match' why.
tp_real = pb.match_topic_persona(CAT13, "write a marketing funnel email sequence",
                                 semantic_pick="brunson-dotcom-secrets")
if (tp_real and tp_real["persona_id"] == "brunson-dotcom-secrets"
        and tp_real["matched_tokens"] and "its topics[] match" in tp_real["why"]):
    ok("a real topics[] hit still returns the persona with an accurate rationale")
else:
    bad(f"real topic-hit rationale wrong: {tp_real}")

# Through the BUNDLE on a 1.3 catalog: a no-topic-match job inherits the semantic
# pick with an HONEST why, and NEVER the '[] (0 signal(s))' misclaim.
paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b10 = pb.build_bundle("update the readme file", "operations", paths=paths, db_path=db,
                      use_llm=False, record=False)
why10 = b10["voice"]["topic_persona"]["why"]
if ("no topics[] tag in the catalog matched this job" in why10
        and "match the job on []" not in why10 and "(0 signal(s))" not in why10):
    ok("1.3 no-match bundle: honest 'no topics[] tag ... matched' rationale (no false claim)")
else:
    bad(f"1.3 no-match rationale dishonest: {why10!r}")

# On a 1.2 catalog the rationale correctly says the catalog has NO topics[] at all.
paths, db = _hermetic(FIXTURE_12, ICP_FOUNDERS)
b10b = pb.build_bundle("write a marketing funnel email sequence", "marketing",
                       paths=paths, db_path=db, use_llm=False, record=False)
why10b = b10b["voice"]["topic_persona"]["why"]
if ("catalog has no topics[] tags to reason over" in why10b
        and "match the job on []" not in why10b):
    ok("1.2 catalog: honest 'catalog has no topics[] tags' rationale")
else:
    bad(f"1.2 rationale wrong: {why10b!r}")


# ═══════════════════════════════════════════════════════════════════════════════
section("T11  MULTI-AUDIENCE (asked) — do NOT pre-commit the arbitrary first voice")

# A company with MULTIPLE known audiences whose FIRST descriptor happens to match a
# real audience persona (shonda) must NOT have that voice pre-selected before the
# operator chooses: audience_persona stays None, the directive is the neutral
# house-voice branch, the write is still gated, and the ASK enumerates EVERY
# candidate. On the pre-fix code shonda's voice was pre-committed here.
ICP_MULTI_MATCH = {"audiences": ["Black women entrepreneurs", "financial beginners in debt"]}
paths, db = _hermetic(FIXTURE_13, ICP_MULTI_MATCH)
b11 = pb.build_bundle("write a marketing funnel email sequence", "marketing",
                      paths=paths, db_path=db, use_llm=False, record=False)
ra11 = b11["resolved_audience"]
if (ra11["source"] == "asked" and b11["confirm_required"] is True
        and b11["voice"]["audience_persona"] is None
        and b11["voice"]["collapsed"] is False
        and "Audience not yet confirmed" in b11["blend_directive"]
        and all(c in ra11["ask"] for c in ("Black women entrepreneurs",
                                           "financial beginners in debt"))):
    ok("multi-audience: no voice pre-committed, neutral directive, write gated, ASK lists all")
else:
    bad(f"multi-audience pre-committed a voice: audience={b11['voice']['audience_persona']} "
        f"collapsed={b11['voice']['collapsed']} directive={b11['blend_directive'][:60]!r}")

# NO-WEAKENING: a SINGLE-ICP onboarding audience is still pre-proposed (the confirm
# prompt shows the one known voice) — proving the suppression is scoped to the
# unconfirmed-multi case only and does not gut the single-audience confirm flow.
paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b11s = pb.build_bundle("write a marketing funnel email sequence to launch our fund",
                       "marketing", paths=paths, db_path=db, use_llm=False, record=False)
if (b11s["resolved_audience"]["source"] == "onboarding_icp"
        and b11s["voice"]["audience_persona"] is not None
        and b11s["voice"]["audience_persona"]["id"] == "shonda-year-of-yes"
        and b11s["confirm_required"] is True):
    ok("NO-WEAKENING: single-ICP still pre-proposes the one known audience voice (confirm prompt)")
else:
    bad(f"single-ICP suppression regression: {b11s['voice']['audience_persona']} "
        f"source={b11s['resolved_audience']['source']}")


# ═══════════════════════════════════════════════════════════════════════════════
section("T12  D8 — OPENCLAW_COMPANY_CONFIG WIRES ideal_customer TO THE MATCHER")


def _fresh_selector_module():
    """Load a PRISTINE persona-selector-v2.py copy, independent of pb._selector()'s
    module-level cache (T1-T11 monkeypatch load_company_config on that cached
    instance). This is what makes T12 a REAL end-to-end proof of the D8 fix rather
    than another mock of it: get_openclaw_paths() and load_company_config() below
    are the actual shipped functions, unmodified."""
    return _load(SCRIPTS / "persona-selector-v2.py", "persona_selector_v2_d8_fresh")


def _with_env(**overrides):
    """Context-manager-free save/restore helper for os.environ (used twice below)."""
    saved = {k: os.environ.get(k) for k in overrides}
    for k, v in overrides.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return saved


def _restore_env(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


_icp_dir = Path(tempfile.mkdtemp(prefix="d8-icp-"))
_icp_fixture = _icp_dir / "company-config.json"
_icp_fixture.write_text(json.dumps({
    "schema_version": "2.0",
    "company": {"ideal_customer": "D8 regression-lock ICP"},
}))

try:
    _saved = _with_env(OPENCLAW_PLATFORM="mac", OPENCLAW_COMPANY_CONFIG=str(_icp_fixture))
    try:
        sel_fresh = _fresh_selector_module()
        d8_paths = sel_fresh.get_openclaw_paths()
        if str(d8_paths.get("company_config")) == str(_icp_fixture):
            ok("get_openclaw_paths() honors the OPENCLAW_COMPANY_CONFIG override")
        else:
            bad(f"company_config not overridden: {d8_paths.get('company_config')}")

        d8_cfg = sel_fresh.load_company_config(d8_paths)
        d8_icp = (d8_cfg.get("company") or {}).get("ideal_customer", "")
        if d8_icp == "D8 regression-lock ICP":
            ok("load_company_config() (REAL, un-mocked) surfaces ideal_customer from OPENCLAW_COMPANY_CONFIG")
        else:
            bad(f"ideal_customer did not reach load_company_config: {d8_cfg}")

        d8_audience = pb.resolve_audience({}, d8_cfg)
        if (d8_audience.get("label") == "D8 regression-lock ICP"
                and d8_audience.get("source") == "onboarding_icp"
                and d8_audience.get("confirm_required") is True):
            ok("resolve_audience() resolves the OPENCLAW_COMPANY_CONFIG-wired ICP end-to-end")
        else:
            bad(f"resolve_audience() did not resolve the env-wired ICP: {d8_audience}")
    finally:
        _restore_env(_saved)

    # NO-WEAKENING: with OPENCLAW_COMPANY_CONFIG unset, the override must NOT leak —
    # company_config must fall back to the company_dir-derived default, never keep
    # pointing at the fixture from the block above (proves the override is read
    # fresh every call, not cached/sticky across get_openclaw_paths() invocations).
    _saved2 = _with_env(OPENCLAW_PLATFORM="mac", OPENCLAW_COMPANY_CONFIG=None)
    try:
        sel_fresh2 = _fresh_selector_module()
        d8_paths2 = sel_fresh2.get_openclaw_paths()
        if str(d8_paths2.get("company_config")) != str(_icp_fixture):
            ok("NO-WEAKENING: company_config falls back to the derived path when "
               "OPENCLAW_COMPANY_CONFIG is unset (no stale leak from a prior override)")
        else:
            bad(f"company_config still points at the D8 fixture with the override "
                f"unset: {d8_paths2.get('company_config')}")
    finally:
        _restore_env(_saved2)
finally:
    shutil.rmtree(_icp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 72)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 72)
sys.exit(0 if FAIL == 0 else 1)
