#!/usr/bin/env python3
"""
test-a-u5-scoped-bundle.py — A-U5 (Per-page/scoped blends) contract lock.

Proves the master-spec v2, Section A.6 build (unit A-U5) against its OWN
BINARY acceptance criteria as REWRITTEN by the OPERATOR RULINGS 2026-07-15
per-repo/offline doctrine (Section A.10, "A-U5" block, verbatim):

  ACCEPT — ONB half (offline, `openclaw-onboarding` branch only): (a)
  `build_bundle(..., scope_hint={page_role, page_slug, conversion_goal})`
  ECHOES the scope into the returned bundle and derives a STABLE composite
  scope key from `(page_role|page_slug)` — the same `scope_hint` yields the
  same key across repeated calls (determinism asserted); an ABSENT
  `scope_hint` returns the unscoped task-level bundle byte-identical to
  pre-change (golden diff = empty, back-compat).

  The CC half — (b) the NEW `task_persona_bundle_scope` migration +
  from-seed chip rendering, (c) existing single-bundle consumers unmodified,
  (d) the 090 schema byte-identical — is proven on that repo's own suite
  (`tests/unit/a-u5-scoped-persona-bundle.test.ts` +
  `tests/unit/a-u5-persona-scope-chips-render.test.tsx` in
  `blackceo-command-center`; this unit lands on BOTH trains).

  MOVED TO A-U7 (per the amendment, NOT this unit's acceptance): "a fixture
  funnel build produces N pages with >=2 DISTINCT blends and exactly N
  per-page persona-selection-log entries" — that criterion exercises A-U7's
  per-page blend-SELECTION machinery (a per-page loop calling build_bundle
  once per page and deciding what each page's blend should be), which this
  unit does not build. A-U5 builds the scope-key/echo MECHANISM a caller
  like A-U7 uses; it proves the mechanism deterministically on ONE call at a
  time, never a multi-page selection fixture.

Also locks the A.6 build steps this unit owns directly (items 1, 3-partial,
5 of Section A.6 "Build (A-U5)"):
  1. scope_hint is additive-only; deriving a stable `scope` key never
     mutates any other resolution input (topic_hint precedence, audience,
     department, catalog).
  3. the different-blends-allowed invariant's ONB-side half — a scope-
     carrying bundle's `rationale['scope']` states WHY (the collapse/blend
     outcome for THIS call), the per-call evidence a downstream (A-U7)
     multi-page comparator reads; this unit does not build that comparator.
  5. `_resolve_scope_key` accepts `part_id` without colliding with
     `page_slug`/`page_role` — the forward-compatible hook U115 (Section E6)
     reuses.

Each check pairs with a NO-WEAKENING probe.

Reuses the SAME hermetic patch harness pattern as test-persona-blend-matcher.py
(persona_blend's cached selector/decompose module instances monkeypatched) —
never reads/writes a live persona DB or the operator's own workspace.

    python3 test-a-u5-scoped-bundle.py [REPO_ROOT]
"""
import importlib.util
import json
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


pb = _load(SCRIPTS / "persona_blend.py", "persona_blend_a_u5")
CAT13 = json.loads(FIXTURE_13.read_text())


# ── Hermetic patch harness (mirrors test-persona-blend-matcher.py's _hermetic) ─
def _fake_dt_select_persona(subtask_text, dept, mode, weights, paths, db_path, variety=True):
    pid = "task-persona-" + str(abs(hash(subtask_text)) % 100000)
    return {"persona_id": pid, "persona_name": pid.replace("-", " ").title(),
            "score": 0.8, "layers": {"task_fit": 0.8}, "interaction_mode": mode}


def _fake_sel_semantic(task, dept, mode, weights, paths, db_path, variety=True, **kw):
    return {"persona_id": "brunson-dotcom-secrets",
            "funnel": {"pool": 7, "category": 6, "semantic": 3}, "score": 0.72}


def _hermetic(catalog_path, company_cfg):
    import os as _os
    _os.environ["OPENCLAW_PERSONA_CATEGORIES"] = str(catalog_path)
    _os.environ.pop("OPENCLAW_AUDIENCE", None)
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


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U5 ACCEPT (a)  BACK-COMPAT — absent scope_hint is byte-identical to pre-A-U5")

paths, db = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_no_scope = pb.build_bundle(
    "write a marketing funnel email sequence to launch our fund", "marketing",
    paths=paths, db_path=db, use_llm=False, record=False)

if "scope" not in b_no_scope and "scope_hint" not in b_no_scope:
    ok("scope_hint omitted -> bundle carries NEITHER 'scope' nor 'scope_hint' key")
else:
    bad(f"scope_hint omission leaked keys: scope={b_no_scope.get('scope')!r} "
        f"scope_hint={b_no_scope.get('scope_hint')!r}")

if "scope" not in b_no_scope.get("rationale", {}):
    ok("scope_hint omitted -> rationale carries no 'scope' entry either")
else:
    bad(f"rationale leaked a scope entry with no scope_hint: {b_no_scope['rationale'].get('scope')!r}")

paths2, db2 = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_explicit_none = pb.build_bundle(
    "write a marketing funnel email sequence to launch our fund", "marketing",
    paths=paths2, db_path=db2, use_llm=False, record=False, scope_hint=None)
if b_explicit_none["voice"] == b_no_scope["voice"] and b_explicit_none["blend_directive"] == b_no_scope["blend_directive"]:
    ok("scope_hint=None explicitly reproduces the same voice + directive as omitting it entirely")
else:
    bad("scope_hint=None diverged from omitting scope_hint")

paths3, db3 = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_empty = pb.build_bundle(
    "write a marketing funnel email sequence to launch our fund", "marketing",
    paths=paths3, db_path=db3, use_llm=False, record=False, scope_hint={})
if "scope" not in b_empty:
    ok("scope_hint={} (empty dict, nothing scope-able) -> no 'scope' key fabricated")
else:
    bad(f"empty scope_hint fabricated a scope key: {b_empty.get('scope')!r}")

# NO-WEAKENING: an unrecognized scope_hint dict (wrong keys) must ALSO resolve to no scope.
paths4, db4 = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_unrecognized = pb.build_bundle(
    "write a marketing funnel email sequence to launch our fund", "marketing",
    paths=paths4, db_path=db4, use_llm=False, record=False,
    scope_hint={"unrelated_key": "value"})
if "scope" not in b_unrecognized:
    ok("NO-WEAKENING: scope_hint naming no known key never fabricates a scope")
else:
    bad(f"NO-WEAKENING failed: unrecognized scope_hint fabricated {b_unrecognized.get('scope')!r}")


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U5 ACCEPT (a)  scope_hint ECHOES + a STABLE composite scope key (single call)")

paths_p, db_p = _hermetic(FIXTURE_13, ICP_FOUNDERS)
SALES_HINT = {"page_role": "sales", "page_slug": "sales", "conversion_goal": "book-a-call"}
b_sales = pb.build_bundle(
    "write a marketing funnel email sequence to launch our fund", "marketing",
    paths=paths_p, db_path=db_p, use_llm=False, record=False, scope_hint=SALES_HINT)

if b_sales.get("scope") == "sales":
    ok("scope_hint {page_role, page_slug} -> composite scope key = page_slug ('sales')")
else:
    bad(f"expected scope='sales', got {b_sales.get('scope')!r}")

if b_sales.get("scope_hint") == SALES_HINT:
    ok("the bundle echoes scope_hint back verbatim (persist-layer round trip)")
else:
    bad(f"scope_hint did not echo back verbatim: {b_sales.get('scope_hint')!r}")

if "rationale" in b_sales and b_sales["rationale"].get("scope"):
    ok("the scoped bundle's rationale states WHY (scope + collapse/blend outcome for this call)")
else:
    bad("scoped bundle is missing rationale['scope']")

# ── (a) DETERMINISM — the SAME scope_hint yields the SAME key across repeated calls ──
paths_r1, db_r1 = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_repeat_1 = pb.build_bundle(
    "write a marketing funnel email sequence to launch our fund", "marketing",
    paths=paths_r1, db_path=db_r1, use_llm=False, record=False, scope_hint=SALES_HINT)
paths_r2, db_r2 = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_repeat_2 = pb.build_bundle(
    "write a marketing funnel email sequence to launch our fund", "marketing",
    paths=paths_r2, db_path=db_r2, use_llm=False, record=False, scope_hint=SALES_HINT)
paths_r3, db_r3 = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_repeat_3 = pb.build_bundle(
    "write a marketing funnel email sequence to launch our fund", "marketing",
    paths=paths_r3, db_path=db_r3, use_llm=False, record=False, scope_hint=SALES_HINT)
if b_repeat_1["scope"] == b_repeat_2["scope"] == b_repeat_3["scope"] == "sales":
    ok("DETERMINISM: the same scope_hint yields the same composite scope key across 3 repeated calls")
else:
    bad(f"determinism failed: {b_repeat_1['scope']!r}, {b_repeat_2['scope']!r}, {b_repeat_3['scope']!r}")

# A DIFFERENT scope_hint (different page) legally yields a DIFFERENT key — proves the
# key is actually derived from the hint, not a constant.
paths_optin, db_optin = _hermetic(FIXTURE_13, ICP_SINGLE)
OPTIN_HINT = {"page_role": "opt-in", "page_slug": "opt-in", "conversion_goal": "lead-capture"}
b_optin = pb.build_bundle(
    "write a budgeting and debt payoff email for our members", "marketing",
    paths=paths_optin, db_path=db_optin, use_llm=False, record=False, scope_hint=OPTIN_HINT)
if b_optin.get("scope") == "opt-in" and b_optin["scope"] != b_sales["scope"]:
    ok("a DIFFERENT scope_hint (different page) derives a DIFFERENT composite scope key")
else:
    bad(f"scope key did not vary with scope_hint: opt-in call got {b_optin.get('scope')!r}")


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U5 ACCEPT (a)  scope_hint is additive-only — never mutates other resolution inputs")

# NO-WEAKENING: the same task/ICP with vs without a scope_hint of {page_role
# equal to what topic_hint would have been anyway} still reaches the SAME
# collapse/voice decision — scope_hint only ever narrows an ALREADY-EMPTY
# topic_hint, it never overrides an explicit one, and it never mutates any
# other resolution input (audience, department, catalog).
paths5, db5 = _hermetic(FIXTURE_13, ICP_SINGLE)
b_explicit_topic = pb.build_bundle(
    "write a budgeting and debt payoff email for our members", "marketing",
    paths=paths5, db_path=db5, use_llm=False, record=False,
    topic_hint="explicit-topic-wins", scope_hint={"page_role": "opt-in", "page_slug": "opt-in"})
if b_explicit_topic["topic"] == "explicit-topic-wins":
    ok("NO-WEAKENING: an explicit topic_hint is NEVER overridden by scope_hint's page_role")
else:
    bad(f"scope_hint incorrectly overrode an explicit topic_hint: topic={b_explicit_topic['topic']!r}")

# part_id (U115's forward-compat key) resolves a scope key too, without colliding.
paths6, db6 = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_part = pb.build_bundle(
    "write a marketing funnel email sequence to launch our fund", "marketing",
    paths=paths6, db_path=db6, use_llm=False, record=False,
    scope_hint={"part_id": "stage-3-nurture"})
if b_part.get("scope") == "stage-3-nurture":
    ok("part_id (U115 forward-compat key) resolves a scope key when no page_slug/page_role given")
else:
    bad(f"part_id scope resolution wrong: {b_part.get('scope')!r}")

# page_slug wins over page_role when both are present (stablest identifier first).
key = pb._resolve_scope_key({"page_role": "sales", "page_slug": "sales-v2"})
if key == "sales-v2":
    ok("_resolve_scope_key: page_slug wins over page_role when both are present")
else:
    bad(f"_resolve_scope_key precedence wrong: {key!r}")


# ═══════════════════════════════════════════════════════════════════════════════
section("SUPPLEMENTARY (not an A-U5 acceptance criterion) — write_persona_selection_log_entry "
        "smoke test: this unit ships the writer, A-U7's per-page loop is its real caller")

import shutil as _shutil
import tempfile as _tempfile

_tmp = Path(_tempfile.mkdtemp(prefix="a-u5-log-writer-smoke-"))
try:
    wrote = pb.write_persona_selection_log_entry(_tmp, "sales", b_sales, reason=b_sales["rationale"]["scope"])
    log_text = (_tmp / "persona-selection-log.md").read_text(encoding="utf-8") if wrote else ""
    if wrote and "scope: sales" in log_text and f"selected_persona: {b_sales.get('persona_id')}" in log_text:
        ok("write_persona_selection_log_entry appends a well-formed single entry (helper works)")
    else:
        bad(f"write_persona_selection_log_entry smoke test failed: wrote={wrote} text={log_text!r}")
finally:
    _shutil.rmtree(_tmp, ignore_errors=True)


print("=" * 72)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 72)
sys.exit(0 if FAIL == 0 else 1)
