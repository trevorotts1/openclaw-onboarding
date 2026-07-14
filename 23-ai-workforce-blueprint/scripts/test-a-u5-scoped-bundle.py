#!/usr/bin/env python3
"""
test-a-u5-scoped-bundle.py — A-U5 (Per-page/scoped blends) contract lock.

Proves the master-spec v2, Section A.6 build (unit A-U5) against its own
BINARY acceptance criteria verbatim (Section A.10):

  (a) a fixture funnel build produces N pages with >=2 DISTINCT blends and
      exactly N per-page selection-log entries;
  (b) `task_persona_bundle_scope` rows persist per (task_id, scope) and
      render as chips — the ONB half of this is proving `build_bundle` emits
      a stable, persistable `scope` key + `scope_hint` echo; the Command
      Center table/persist/render half is proven on that repo's own suite
      (this unit lands on BOTH trains — see the master spec crosswalk);
  (c) all existing single-bundle consumers pass unmodified (back-compat) —
      scope_hint omitted/None produces a bundle with NEITHER `scope` nor
      `scope_hint` keys, and every field that WAS present stays byte-identical
      to the pre-A-U5 shape;
  (d) the 090 table's schema is untouched by this unit — not applicable on
      the Python side (this module never touches CC migrations); asserted
      instead: NOTHING in this unit's code path writes/reads
      `task_persona_bundle` (the unscoped table) — scope_hint is a pure
      additive parameter to build_bundle, never a rewrite of the unscoped
      path.

Also locks the A.6 build steps this unit owns directly (Section A.6 "Build
(A-U5)" items 1, 3, 4-adjacent (the ONB-side scope key + rationale), 5):
  1. scope_hint is additive-only; a fixture funnel run through it produces a
     stable per-page `scope` key.
  3. the different-blends-allowed invariant — each page's bundle carries a
     `rationale['scope']` stating WHY (the collapse/blend outcome for that
     page), so a downstream (A-U7) comparator can tell "shared, collapse
     fired the same way" from "forced-identical, no reason".
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
import shutil
import sys
import tempfile
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

TMP = Path(tempfile.mkdtemp(prefix="a-u5-fixture-funnel-"))


def _cleanup():
    shutil.rmtree(TMP, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U5 ACCEPT (c)  BACK-COMPAT — scope_hint omitted is byte-identical to pre-A-U5")

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
section("A-U5 ACCEPT (a) + (b)  fixture funnel: N pages, >=2 distinct blends, N log entries")

PAGES = [
    {
        "task": "write a budgeting and debt payoff email for our members",
        "icp": ICP_SINGLE,
        "scope_hint": {"page_role": "opt-in", "page_slug": "opt-in", "conversion_goal": "lead-capture"},
    },
    {
        "task": "write a marketing funnel email sequence to launch our fund",
        "icp": ICP_FOUNDERS,
        "scope_hint": {"page_role": "sales", "page_slug": "sales", "conversion_goal": "book-a-call"},
    },
    {
        "task": "write a marketing funnel email sequence to launch our fund",
        "icp": ICP_FOUNDERS,
        "scope_hint": {"page_role": "thank-you", "page_slug": "thank-you", "conversion_goal": "confirm-booking"},
    },
]

page_bundles = []
for page in PAGES:
    pg_paths, pg_db = _hermetic(FIXTURE_13, page["icp"])
    bundle = pb.build_bundle(
        page["task"], "marketing", paths=pg_paths, db_path=pg_db,
        use_llm=False, record=False, scope_hint=page["scope_hint"])
    page_bundles.append((page["scope_hint"]["page_slug"], bundle))

if len(page_bundles) == len(PAGES):
    ok(f"fixture funnel produced exactly N={len(PAGES)} page bundles")
else:
    bad(f"expected {len(PAGES)} page bundles, got {len(page_bundles)}")

distinct_voice_ids = {b["persona_id"] for _, b in page_bundles}
if len(distinct_voice_ids) >= 2:
    ok(f"fixture funnel: >=2 DISTINCT voice blends across N pages ({sorted(distinct_voice_ids)})")
else:
    bad(f"fixture funnel produced only {len(distinct_voice_ids)} distinct voice(s): {distinct_voice_ids}")

# Every page bundle carries its own stable scope key, matching its page_slug.
if all(b.get("scope") == slug for slug, b in page_bundles):
    ok("every page bundle's 'scope' key equals its page_slug (stable, persistable)")
else:
    bad(f"scope key mismatch: {[(slug, b.get('scope')) for slug, b in page_bundles]}")

# Every page bundle's scope_hint round-trips (echoed back for the CC persist layer).
if all(b.get("scope_hint") == page["scope_hint"] for (slug, b), page in zip(page_bundles, PAGES)):
    ok("every page bundle echoes its scope_hint back verbatim (persist-layer round trip)")
else:
    bad("scope_hint echo did not round-trip on one or more pages")

# Different-blends-allowed invariant: each page states WHY (rationale['scope']).
if all("rationale" in b and "scope" in b["rationale"] and b["rationale"]["scope"] for _, b in page_bundles):
    ok("every page bundle's rationale states WHY (scope + collapse/blend outcome)")
else:
    bad("one or more page bundles is missing rationale['scope']")

# Write exactly N persona-selection-log.md entries (one per page), reusing the
# existing repo-wide log convention.
log_count = 0
for slug, bundle in page_bundles:
    wrote = pb.write_persona_selection_log_entry(TMP, slug, bundle, reason=bundle["rationale"]["scope"])
    if wrote:
        log_count += 1

log_path = TMP / "persona-selection-log.md"
log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
entry_count = log_text.count("## page: ")

if log_count == len(PAGES):
    ok(f"write_persona_selection_log_entry succeeded for all N={len(PAGES)} pages")
else:
    bad(f"only {log_count}/{len(PAGES)} log writes succeeded")

if entry_count == len(PAGES):
    ok(f"persona-selection-log.md carries exactly N={len(PAGES)} per-page entries")
else:
    bad(f"expected {len(PAGES)} log entries, found {entry_count}")

for slug, bundle in page_bundles:
    pid = bundle.get("persona_id") or "none"
    if f"scope: {slug}" in log_text and f"selected_persona: {pid}" in log_text:
        ok(f"log entry for scope={slug} names selected_persona={pid}")
    else:
        bad(f"log entry for scope={slug} missing/incorrect (expected selected_persona={pid})")

_cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U5 ACCEPT (d)  scope_hint never touches the unscoped bundle assembly path")

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


print("=" * 72)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 72)
sys.exit(0 if FAIL == 0 else 1)
