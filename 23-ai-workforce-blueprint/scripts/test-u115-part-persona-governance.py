#!/usr/bin/env python3
"""
test-u115-part-persona-governance.py — U115 (E6-1; implements operator ruling
ADD-1; closes G7) contract lock: per-part / per-persona governance across
multi-item & long-horizon tasks.

Proves the master-spec Section E6 BINARY acceptance criteria for this unit's
ONB (openclaw-onboarding) leg — the Command Center leg (board card + task-
detail modal per-part row, criterion (c)) is OUT OF SCOPE for this repo and
is NOT exercised here; it is logged as owed for the blackceo-command-center
train, same per-repo/offline doctrine A-U5 (Section A.10) already
established for this exact split.

  (a) a fixture multi-part task decomposes into its parts and produces one
      governing bundle PER PART, with >=2 parts carrying DISTINCT blends
      each with its own audience + topic (part count == bundle-scope
      count) — PASS/FAIL.
  (b) `routing/part-persona-map.json` records which blend governs each
      part/stage and a long-horizon fixture (multi-stage sequence) tracks
      the assignment across ALL stages — PASS/FAIL.
  (c) OWED (Command Center leg — board card + task-detail modal render).
  (d) a task with no declared parts degrades to today's single task-level
      bundle byte-identically (back-compat golden) — PASS/FAIL.
  (e) forced-identical blends across all parts with no logged reason is
      flagged (hands to U117), while a legitimately shared blend with a
      logged reason passes — PASS/FAIL.

Also locks the mechanism-reuse invariant (spec `revert:` clause / Section E6
framing): U115 reuses A-U5's `scope`/`scope_hint` echo + `_resolve_scope_key`
`part_id` hook verbatim (no new bundle store, no new scope-resolution logic)
and sits behind `PER_PART_GOVERNANCE=1` (unset/non-"1" => byte-identical
pre-U115 behavior).

Reuses the SAME hermetic patch harness pattern as test-a-u5-scoped-bundle.py
(persona_blend's cached selector/decompose module instances monkeypatched) —
never reads/writes a live persona DB or the operator's own workspace.

    python3 test-u115-part-persona-governance.py [REPO_ROOT]
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


pb = _load(SCRIPTS / "persona_blend.py", "persona_blend_u115")


# ── Hermetic patch harness (mirrors test-a-u5-scoped-bundle.py's _hermetic) ────
def _fake_dt_select_persona(subtask_text, dept, mode, weights, paths, db_path, variety=True):
    pid = "task-persona-" + str(abs(hash(subtask_text)) % 100000)
    return {"persona_id": pid, "persona_name": pid.replace("-", " ").title(),
            "score": 0.8, "layers": {"task_fit": 0.8}, "interaction_mode": mode}


def _fake_sel_semantic_neutral(task, dept, mode, weights, paths, db_path, variety=True, **kw):
    # No semantic nudge — lets each part's OWN topic_hint decide its topic
    # persona on its own merits (BINARY (a) needs genuinely distinct picks,
    # not a constant semantic-selector thumb on the scale).
    return {"persona_id": "", "funnel": {"pool": 7, "category": 6, "semantic": 0}, "score": 0.0}


def _hermetic(catalog_path, company_cfg):
    os.environ["OPENCLAW_PERSONA_CATEGORIES"] = str(catalog_path)
    os.environ.pop("OPENCLAW_AUDIENCE", None)
    sel = pb._selector()
    dt = pb._decompose()
    sel.load_company_config = lambda paths: company_cfg
    sel.select_persona = _fake_sel_semantic_neutral
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

TASK_CAMPAIGN = "write the campaign package across all its parts"
TASK_SUGGESTIVE_NO_STRUCTURE = ("write a sales page, three nurture emails, "
                                "and two social posts for the launch")


def _strip_nondeterministic(bundle):
    """`task_id` is generated fresh (non-deterministic) by the underlying
    task-decomposition module on EVERY build_bundle call regardless of
    U115 — even two back-to-back calls with identical inputs disagree on
    it (pre-existing behavior, verified against this module unmodified).
    The byte-identical back-compat checks below compare everything else.
    """
    b = dict(bundle)
    b.pop("task_id", None)
    return b


def _set_flag(value):
    if value is None:
        os.environ.pop(pb.PER_PART_GOVERNANCE_FLAG, None)
    else:
        os.environ[pb.PER_PART_GOVERNANCE_FLAG] = value


CAMPAIGN_MANIFEST = {
    "parts": [
        {"part_id": "sales-page", "part_role": "sales", "topic_hint": "funnels"},
        {"part_id": "nurture-email-1", "part_role": "nurture-email",
         "topic_hint": "budgeting", "stage": 1},
        {"part_id": "nurture-email-2", "part_role": "nurture-email",
         "topic_hint": "budgeting", "stage": 2},
        {"part_id": "nurture-email-3", "part_role": "nurture-email",
         "topic_hint": "budgeting", "stage": 3},
        {"part_id": "social-1", "part_role": "social",
         "topic_hint": "storytelling", "stage": 1},
        {"part_id": "social-2", "part_role": "social",
         "topic_hint": "storytelling", "stage": 2},
    ]
}


# ═══════════════════════════════════════════════════════════════════════════════
section("U115 build step 1 — decompose_task_parts: MECHANICAL sources, NEVER invents")

parts = pb.decompose_task_parts(TASK_CAMPAIGN, campaign_manifest=CAMPAIGN_MANIFEST)
if len(parts) == 6:
    ok("campaign_manifest['parts'] (6 parts: 1 sales + 3 nurture + 2 social) decomposes mechanically")
else:
    bad(f"expected 6 parts from campaign_manifest, got {len(parts)}: {parts!r}")

if parts and parts[0] == {"part_id": "sales-page", "part_role": "sales",
                          "audience_hint": "", "topic_hint": "funnels", "stage": "1"}:
    ok("decomposed part carries the generic {part_id, part_role, audience_hint, topic_hint, stage} shape")
else:
    bad(f"decomposed part shape wrong: {parts[0] if parts else None!r}")

# alt key name: "stages" (a long-horizon manifest may call its list "stages")
manifest_stages = {"stages": [{"id": "stage-1", "role": "launch-email", "topic": "funnels"},
                              {"id": "stage-2", "role": "follow-up", "topic": "budgeting"}]}
parts_stages = pb.decompose_task_parts(TASK_CAMPAIGN, campaign_manifest=manifest_stages)
if [p["part_id"] for p in parts_stages] == ["stage-1", "stage-2"]:
    ok("campaign_manifest['stages'] (alt key) also decomposes mechanically")
else:
    bad(f"'stages' key decomposition wrong: {parts_stages!r}")

# funnel pageStructure (06-ghl-install-pages/funnel-templates/** shape: order/page/purpose)
PAGE_STRUCTURE = [
    {"order": 1, "page": "Opt-In Page", "purpose": "lead capture"},
    {"order": 2, "page": "Sales Page", "page_role": "sales", "page_slug": "sales-v2",
     "purpose": "convert to buyer"},
]
parts_ps = pb.decompose_task_parts(TASK_CAMPAIGN, page_structure=PAGE_STRUCTURE)
if len(parts_ps) == 2 and parts_ps[0]["part_id"] == "opt-in-page" and parts_ps[0]["part_role"] == "opt-in-page":
    ok("pageStructure entry with no explicit page_role slugifies its 'page' name mechanically")
else:
    bad(f"pageStructure->part_id slugify wrong: {parts_ps!r}")
if parts_ps[1]["part_id"] == "sales-v2" and parts_ps[1]["part_role"] == "sales":
    ok("pageStructure entry with explicit page_role/page_slug uses them directly (never re-derives)")
else:
    bad(f"pageStructure explicit page_role/page_slug not honored: {parts_ps[1]!r}")

# campaign_manifest takes precedence over page_structure when BOTH are supplied
parts_both = pb.decompose_task_parts(TASK_CAMPAIGN, campaign_manifest=CAMPAIGN_MANIFEST,
                                     page_structure=PAGE_STRUCTURE)
if len(parts_both) == 6:
    ok("campaign_manifest takes precedence over page_structure when both are supplied")
else:
    bad(f"precedence wrong: expected 6 (campaign_manifest), got {len(parts_both)}")

# malformed / empty sources
for label, kwargs in [
    ("empty campaign_manifest dict", {"campaign_manifest": {}}),
    ("campaign_manifest with no parts/stages key", {"campaign_manifest": {"other": 1}}),
    ("campaign_manifest.parts not a list", {"campaign_manifest": {"parts": "nope"}}),
    ("empty page_structure list", {"page_structure": []}),
    ("page_structure not a list", {"page_structure": {"not": "a list"}}),
]:
    result = pb.decompose_task_parts(TASK_CAMPAIGN, **kwargs)
    if result == []:
        ok(f"malformed/empty source ({label}) -> [] (never invents)")
    else:
        bad(f"malformed/empty source ({label}) fabricated parts: {result!r}")

# NO-WEAKENING: a task whose TEXT strongly suggests multiple parts, but with
# NEITHER structured source supplied, still returns [] — never invents parts
# from prose alone (ASK-gated, ADD-1's "never invents parts silently").
parts_suggestive = pb.decompose_task_parts(TASK_SUGGESTIVE_NO_STRUCTURE)
if parts_suggestive == []:
    ok("NO-WEAKENING: suggestive task TEXT with no structured source never invents parts (ASK-gated)")
else:
    bad(f"decompose_task_parts invented parts from prose alone: {parts_suggestive!r}")

# a pageStructure entry naming no page at all is skipped, never guessed
parts_unnamed = pb.decompose_task_parts(TASK_CAMPAIGN,
                                        page_structure=[{"order": 1, "purpose": "no name here"}])
if parts_unnamed == []:
    ok("NO-WEAKENING: a pageStructure entry with no page/page_role/role name is skipped, not guessed")
else:
    bad(f"unnamed pageStructure entry was not skipped: {parts_unnamed!r}")


# ═══════════════════════════════════════════════════════════════════════════════
section("BINARY (d) — PER_PART_GOVERNANCE flag-gated back-compat (byte-identical golden)")

paths_a, db_a = _hermetic(FIXTURE_13, ICP_FOUNDERS)
b_direct = pb.build_bundle(TASK_CAMPAIGN, "marketing", paths=paths_a, db_path=db_a,
                           use_llm=False, record=False)

_set_flag(None)  # flag unset (default) -> single, even with parts explicitly supplied
paths_b, db_b = _hermetic(FIXTURE_13, ICP_FOUNDERS)
r_flag_off = pb.govern_task_parts(TASK_CAMPAIGN, "marketing", parts=CAMPAIGN_MANIFEST["parts"],
                                  paths=paths_b, db_path=db_b, use_llm=False, record=False)
if r_flag_off["mode"] == "single" and _strip_nondeterministic(r_flag_off["bundle"]) == _strip_nondeterministic(b_direct):
    ok("PER_PART_GOVERNANCE unset -> mode='single', byte-identical to build_bundle() even with parts= supplied")
else:
    bad(f"flag-off did not degrade byte-identically: mode={r_flag_off['mode']!r}")

_set_flag("0")
paths_c, db_c = _hermetic(FIXTURE_13, ICP_FOUNDERS)
r_flag_zero = pb.govern_task_parts(TASK_CAMPAIGN, "marketing", parts=CAMPAIGN_MANIFEST["parts"],
                                   paths=paths_c, db_path=db_c, use_llm=False, record=False)
if r_flag_zero["mode"] == "single":
    ok("NO-WEAKENING: PER_PART_GOVERNANCE='0' is OFF (only literal '1' enables it)")
else:
    bad(f"PER_PART_GOVERNANCE='0' incorrectly enabled per-part mode: {r_flag_zero['mode']!r}")

_set_flag("true")
paths_d, db_d = _hermetic(FIXTURE_13, ICP_FOUNDERS)
r_flag_true = pb.govern_task_parts(TASK_CAMPAIGN, "marketing", parts=CAMPAIGN_MANIFEST["parts"],
                                   paths=paths_d, db_path=db_d, use_llm=False, record=False)
if r_flag_true["mode"] == "single":
    ok("NO-WEAKENING: PER_PART_GOVERNANCE='true' is OFF (only the literal string '1' enables it)")
else:
    bad(f"PER_PART_GOVERNANCE='true' incorrectly enabled per-part mode: {r_flag_true['mode']!r}")

_set_flag("1")
paths_e, db_e = _hermetic(FIXTURE_13, ICP_FOUNDERS)
r_no_parts = pb.govern_task_parts(TASK_CAMPAIGN, "marketing",
                                  paths=paths_e, db_path=db_e, use_llm=False, record=False)
if r_no_parts["mode"] == "single" and _strip_nondeterministic(r_no_parts["bundle"]) == _strip_nondeterministic(b_direct):
    ok("BINARY (d): PER_PART_GOVERNANCE=1 but NO declared parts -> single task-level bundle, byte-identical")
else:
    bad(f"no-declared-parts degrade failed: mode={r_no_parts['mode']!r}")


# ═══════════════════════════════════════════════════════════════════════════════
section("BINARY (a) — one governing bundle PER PART, >=2 DISTINCT blends, part count == scope count")

_set_flag("1")
paths_f, db_f = _hermetic(FIXTURE_13, ICP_FOUNDERS)
result = pb.govern_task_parts(TASK_CAMPAIGN, "marketing", campaign_manifest=CAMPAIGN_MANIFEST,
                              paths=paths_f, db_path=db_f, use_llm=False, record=False)

if result["mode"] == "per_part":
    ok("mode='per_part' when PER_PART_GOVERNANCE=1 and parts are declared")
else:
    bad(f"expected mode='per_part', got {result['mode']!r}")

if len(result["parts"]) == 6:
    ok("one governing bundle produced PER PART (6 parts -> 6 bundles)")
else:
    bad(f"expected 6 per-part bundles, got {len(result['parts'])}")

scopes = [pr["bundle"].get("scope") for pr in result["parts"]]
part_ids = [pr["part_id"] for pr in result["parts"]]
if scopes == part_ids and len(set(scopes)) == len(scopes) == 6:
    ok("part count == distinct bundle-scope count (6 == 6), each scope == its own part_id")
else:
    bad(f"scope/part_id mismatch: scopes={scopes!r} part_ids={part_ids!r}")

persona_ids = [pr["bundle"].get("persona_id") for pr in result["parts"]]
if len(set(persona_ids)) >= 2:
    ok(f"BINARY (a): >=2 DISTINCT governing blends across parts ({len(set(persona_ids))} distinct: {sorted(set(persona_ids))})")
else:
    bad(f"expected >=2 distinct blends, got only {set(persona_ids)!r}")

if all(pr["bundle"].get("topic") for pr in result["parts"]) and \
   all(pr["bundle"].get("resolved_audience", {}).get("label") for pr in result["parts"]):
    ok("every part's bundle carries its OWN audience + topic (non-empty on all 6)")
else:
    bad("some part's bundle is missing an audience or topic")


# ═══════════════════════════════════════════════════════════════════════════════
section("Mechanism reuse — U115 reuses A-U5's scope_hint echo verbatim (no new resolution logic)")

sales_bundle = next(pr["bundle"] for pr in result["parts"] if pr["part_id"] == "sales-page")
if sales_bundle.get("scope_hint") == {"part_id": "sales-page"}:
    ok("the per-part scope_hint echoed onto the bundle is EXACTLY {'part_id': ...} — A-U5's own contract, untouched")
else:
    bad(f"scope_hint echo diverged from A-U5's contract: {sales_bundle.get('scope_hint')!r}")

if pb._resolve_scope_key({"part_id": "sales-page"}) == "sales-page":
    ok("U115 drives A-U5's existing `_resolve_scope_key` part_id branch directly — no duplicate key-resolution logic")
else:
    bad("_resolve_scope_key part_id branch regressed")


# ═══════════════════════════════════════════════════════════════════════════════
section("BINARY (b) — routing/part-persona-map.json: per-part tracking, cross-horizon accumulation")

_tmp = Path(tempfile.mkdtemp(prefix="u115-part-map-"))
try:
    _set_flag("1")
    paths_g, db_g = _hermetic(FIXTURE_13, ICP_FOUNDERS)
    stage1_manifest = {"parts": [
        {"part_id": "sales-page", "part_role": "sales", "topic_hint": "funnels", "stage": 1},
        {"part_id": "nurture-email-1", "part_role": "nurture-email", "topic_hint": "budgeting", "stage": 1},
    ]}
    r1 = pb.govern_task_parts(TASK_CAMPAIGN, "marketing", campaign_manifest=stage1_manifest,
                              run_dir=_tmp, paths=paths_g, db_path=db_g, use_llm=False, record=False)

    map_path = _tmp / "routing" / "part-persona-map.json"
    if map_path.exists():
        ok("routing/part-persona-map.json is written under run_dir after stage 1")
    else:
        bad("routing/part-persona-map.json was not written")

    on_disk_1 = json.loads(map_path.read_text(encoding="utf-8")) if map_path.exists() else []
    if len(on_disk_1) == 2 and {r["part_id"] for r in on_disk_1} == {"sales-page", "nurture-email-1"}:
        ok("stage 1: map records BOTH parts with the same ids govern_task_parts returned")
    else:
        bad(f"stage 1 map content wrong: {on_disk_1!r}")

    if all(set(r.keys()) >= {"part_id", "part_role", "voice_persona_id", "topic_persona_id",
                             "audience_label", "audience_source", "stage"} for r in on_disk_1):
        ok("each map record carries the spec-named keys (part_id, part_role, voice_persona_id, "
           "topic_persona_id, audience_label, audience_source, stage)")
    else:
        bad(f"map record missing a spec-named key: {on_disk_1!r}")

    # ── LONG-HORIZON: stage 2, same run_dir, DIFFERENT parts — must ACCUMULATE, not clobber ──
    paths_h, db_h = _hermetic(FIXTURE_13, ICP_FOUNDERS)
    stage2_manifest = {"parts": [
        {"part_id": "social-1", "part_role": "social", "topic_hint": "storytelling", "stage": 2},
    ]}
    r2 = pb.govern_task_parts(TASK_CAMPAIGN, "marketing", campaign_manifest=stage2_manifest,
                              run_dir=_tmp, paths=paths_h, db_path=db_h, use_llm=False, record=False)
    on_disk_2 = json.loads(map_path.read_text(encoding="utf-8"))
    if {r["part_id"] for r in on_disk_2} == {"sales-page", "nurture-email-1", "social-1"}:
        ok("BINARY (b): a stage-2 call on the SAME run_dir ACCUMULATES — stage-1 parts still tracked "
           "alongside the new stage-2 part (tracks the assignment across ALL stages)")
    else:
        bad(f"stage 2 did not accumulate on top of stage 1: {on_disk_2!r}")

    # ── REVISION: re-running an EXISTING part_id updates in place, no duplicate ──
    paths_i, db_i = _hermetic(FIXTURE_13, ICP_FOUNDERS)
    revise_manifest = {"parts": [
        {"part_id": "sales-page", "part_role": "sales-REVISED", "topic_hint": "funnels", "stage": "1-revised"},
    ]}
    pb.govern_task_parts(TASK_CAMPAIGN, "marketing", campaign_manifest=revise_manifest,
                         run_dir=_tmp, paths=paths_i, db_path=db_i, use_llm=False, record=False)
    on_disk_3 = json.loads(map_path.read_text(encoding="utf-8"))
    sales_records = [r for r in on_disk_3 if r["part_id"] == "sales-page"]
    if len(on_disk_3) == 3 and len(sales_records) == 1 and sales_records[0]["part_role"] == "sales-REVISED":
        ok("revising an existing part_id UPDATES its record in place (no duplicate row, still 3 total)")
    else:
        bad(f"revision did not merge in place: {on_disk_3!r}")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)

# write_part_persona_map direct: merge=False replaces wholesale
_tmp2 = Path(tempfile.mkdtemp(prefix="u115-part-map-wholesale-"))
try:
    pb.write_part_persona_map(_tmp2, [{"part_id": "a", "voice_persona_id": "x"}])
    pb.write_part_persona_map(_tmp2, [{"part_id": "b", "voice_persona_id": "y"}], merge=False)
    on_disk = json.loads((_tmp2 / "routing" / "part-persona-map.json").read_text(encoding="utf-8"))
    if [r["part_id"] for r in on_disk] == ["b"]:
        ok("write_part_persona_map(merge=False) replaces the map wholesale (part 'a' dropped)")
    else:
        bad(f"merge=False did not replace wholesale: {on_disk!r}")
finally:
    shutil.rmtree(_tmp2, ignore_errors=True)

# malformed records (missing part_id) never crash the writer, never get written
_tmp3 = Path(tempfile.mkdtemp(prefix="u115-part-map-malformed-"))
try:
    wrote = pb.write_part_persona_map(_tmp3, [{"no_part_id": "here"}, {"part_id": "", "x": 1},
                                              {"part_id": "real", "voice_persona_id": "z"}])
    on_disk = json.loads((_tmp3 / "routing" / "part-persona-map.json").read_text(encoding="utf-8"))
    if wrote and [r["part_id"] for r in on_disk] == ["real"]:
        ok("write_part_persona_map skips malformed/empty-part_id records without crashing")
    else:
        bad(f"malformed record handling wrong: wrote={wrote} on_disk={on_disk!r}")
finally:
    shutil.rmtree(_tmp3, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════════
section("BINARY (e) — forced-identical-with-no-reason FLAGGED; legitimately-shared PASSES")

forced_no_reason = [
    {"part_id": "p1", "voice_persona_id": "same-persona", "reason": ""},
    {"part_id": "p2", "voice_persona_id": "same-persona", "reason": None},
    {"part_id": "p3", "voice_persona_id": "same-persona", "reason": ""},
]
v1 = pb.validate_part_blend_diversity(forced_no_reason)
if v1["ok"] is False and v1["forced_identical"] is True and v1["flagged_groups"]:
    ok("BINARY (e): forced-identical blend with NO logged reason is FLAGGED (ok=False, hands to U117)")
else:
    bad(f"forced-identical-no-reason was not flagged: {v1!r}")

legit_shared = [
    {"part_id": "p1", "voice_persona_id": "same-persona",
     "reason": "scope=p1 — collapsed onto same-persona — blend shared with part(s) p2, p3"},
    {"part_id": "p2", "voice_persona_id": "same-persona",
     "reason": "scope=p2 — collapsed onto same-persona — blend shared with part(s) p1, p3"},
    {"part_id": "p3", "voice_persona_id": "same-persona",
     "reason": "scope=p3 — collapsed onto same-persona — blend shared with part(s) p1, p2"},
]
v2 = pb.validate_part_blend_diversity(legit_shared)
if v2["ok"] is True and v2["forced_identical"] is True and v2["flagged_groups"] == []:
    ok("BINARY (e): a legitimately shared blend WITH a logged reason on every part PASSES (not flagged)")
else:
    bad(f"legitimately-shared-with-reason was incorrectly flagged: {v2!r}")

partial_reason = [
    {"part_id": "p1", "voice_persona_id": "same-persona", "reason": "stated why"},
    {"part_id": "p2", "voice_persona_id": "same-persona", "reason": ""},
]
v3 = pb.validate_part_blend_diversity(partial_reason)
if v3["ok"] is False and v3["flagged_groups"][0]["unreasoned_part_ids"] == ["p2"]:
    ok("NO-WEAKENING: even ONE unreasoned part in a shared-blend group is enough to flag the group")
else:
    bad(f"partial-reason group not correctly flagged: {v3!r}")

all_distinct = [
    {"part_id": "p1", "voice_persona_id": "persona-a", "reason": ""},
    {"part_id": "p2", "voice_persona_id": "persona-b", "reason": ""},
    {"part_id": "p3", "voice_persona_id": "persona-c", "reason": ""},
]
v4 = pb.validate_part_blend_diversity(all_distinct)
if v4["ok"] is True and v4["forced_identical"] is False and v4["flagged_groups"] == []:
    ok("all-distinct blends (no sharing at all) never flag, even with no reason field populated")
else:
    bad(f"all-distinct case incorrectly flagged: {v4!r}")

v5 = pb.validate_part_blend_diversity([{"part_id": "p1", "voice_persona_id": "solo", "reason": ""}])
if v5["ok"] is True:
    ok("fewer than 2 parts -> ok=True trivially (nothing to compare)")
else:
    bad(f"single-part case incorrectly flagged: {v5!r}")

# real pipeline: two parts that legitimately land on the SAME persona (identical
# topic_hint) get an AUTO-annotated "shared with part(s)" reason and PASS.
_set_flag("1")
paths_j, db_j = _hermetic(FIXTURE_13, ICP_FOUNDERS)
same_topic_manifest = {"parts": [
    {"part_id": "nurture-email-1", "part_role": "nurture-email", "topic_hint": "budgeting"},
    {"part_id": "nurture-email-2", "part_role": "nurture-email", "topic_hint": "budgeting"},
]}
r_shared = pb.govern_task_parts(TASK_CAMPAIGN, "marketing", campaign_manifest=same_topic_manifest,
                                paths=paths_j, db_path=db_j, use_llm=False, record=False)
shared_map = r_shared["part_persona_map"]
same_persona = len({r["voice_persona_id"] for r in shared_map}) == 1
all_reasoned = all("shared with part" in (r.get("reason") or "") for r in shared_map)
v_real = pb.validate_part_blend_diversity(shared_map)
if same_persona and all_reasoned and v_real["ok"] is True:
    ok("real pipeline: 2 parts genuinely collapsing onto the same persona get an "
       "auto-annotated 'shared with part(s)' reason and validate_part_blend_diversity PASSES")
else:
    bad(f"real shared-blend pipeline did not self-annotate correctly: same_persona={same_persona} "
        f"all_reasoned={all_reasoned} v_real={v_real!r} map={shared_map!r}")


print("=" * 72)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 72)
sys.exit(0 if FAIL == 0 else 1)
