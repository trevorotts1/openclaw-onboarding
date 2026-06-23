"""End-to-end + negative tests for the full-funnel P0→P5 pipeline (goal #196).

These are the on-fixture integration bites the acceptance checklist names
(T-1..T-9, T-N1..T-N6) plus the funnel_rollback idempotency contract. They run
OFFLINE (no live CRM / Gemini / network) by exercising funnel_fixture_harness +
funnel_rollback + funnel_rubrics against a temp evidence tree.
"""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import funnel_fixture_harness as harness  # noqa: E402
import funnel_rubrics as rubrics  # noqa: E402
from funnel_rollback import FunnelRollbackInputs, run_funnel_rollback  # noqa: E402


@pytest.fixture
def happy_run(tmp_path):
    run_dir = str(tmp_path / "run")
    ev = harness.build_funnel(run_dir)
    return run_dir, ev


# ── T-1..T-9: the happy-path integration evidence the checklist demands ─────

def test_t1_all_seven_stage_artifacts_exist(happy_run):
    run_dir, _ = happy_run
    fr = os.path.join(run_dir, "working", "funnels", "scent-bar-workshop")
    assert os.path.isfile(os.path.join(fr, "offer-spec.json"))          # P0
    assert os.path.isfile(os.path.join(fr, "funnel-spec.json"))         # P1
    assert os.path.isfile(os.path.join(fr, "persona-selection-log.md")) # P1 grounding
    assert os.path.isfile(os.path.join(run_dir, "working", "copy", "scent-bar-workshop", "copy.md"))   # P2
    assert os.path.isfile(os.path.join(run_dir, "working", "email", "scent-bar-workshop", "email-sequence.json"))  # P2e
    assert os.path.isfile(os.path.join(fr, "assets-manifest.json"))     # P3
    assert os.path.isfile(os.path.join(fr, "build-result.json"))        # P4


def test_t2_offer_spec_has_required_fields(happy_run):
    run_dir, _ = happy_run
    offer = json.load(open(os.path.join(run_dir, "working", "funnels", "scent-bar-workshop", "offer-spec.json")))
    for k in ["product_name", "deliverables", "price_points", "guarantee", "bonuses", "positioning"]:
        assert offer.get(k), f"offer-spec missing {k}"


def test_t3_persona_grounded_on_hormozi_with_real_selector(happy_run):
    run_dir, _ = happy_run
    log = open(os.path.join(run_dir, "working", "funnels", "scent-bar-workshop", "persona-selection-log.md")).read()
    assert "hormozi-100m-offers" in log
    # The real selector ran for the web-development funnel surface (U1 tag widen).
    assert "selector_ran" in log


def test_t4_copy_reaches_approved(happy_run):
    run_dir, _ = happy_run
    copy = open(os.path.join(run_dir, "working", "copy", "scent-bar-workshop", "copy.md")).read()
    assert "status: APPROVED" in copy
    cjson = json.load(open(os.path.join(run_dir, "working", "copy", "scent-bar-workshop", "copy.json")))
    assert cjson["status"] == "APPROVED"


def test_t5_ecosystem_receipts_present(happy_run):
    run_dir, _ = happy_run
    eco = os.path.join(run_dir, "ecosystem")
    for name in ["calendar", "product-price", "optin-form", "contact-test", "workflow"]:
        r = json.load(open(os.path.join(eco, f"{name}.json")))
        assert r["http_status"] == 201 and r["qc_passed"]


def test_t6_waiting_on_dependency_used_and_ordering_enforced(happy_run):
    _, ev = happy_run
    assert ev["board"]["waiting_on_dependency_used"] is True
    # Board handoff events fired at P-boundaries (SOP-07 F8).
    slugs = {h["job_id"] for h in ev["board"]["handoffs"]}
    assert {"p1-funnel-spec", "p4-build", "p5-automation"} & slugs


def test_t7_final_preview_verify_is_seven_of_seven(happy_run):
    run_dir, ev = happy_run
    raw = json.load(open(os.path.join(run_dir, "logs", "final-preview-verify.json")))
    assert raw["stages_total"] == 7
    assert raw["stages_complete"] == 7
    assert raw["overall_pass"] is True
    assert ev["parent_done"] is True


def test_t8_verify_summary_consistent_with_raw(happy_run):
    run_dir, _ = happy_run
    raw = json.load(open(os.path.join(run_dir, "logs", "final-preview-verify.json")))
    summary = json.load(open(os.path.join(run_dir, "scorecard", "verify-summary.json")))
    assert summary["passed"] == raw["stages_complete"]
    assert summary["overall_pass"] == raw["overall_pass"]


def test_t9_all_eleven_rubrics_pass(happy_run):
    run_dir, _ = happy_run
    results = rubrics.score_all(run_dir, cc_invariant_ok=True)
    assert {r.id for r in results} == set(rubrics.RUBRIC_IDS)
    for r in results:
        assert r.passed and r.score >= rubrics.THRESHOLD, f"{r.id} scored {r.score}"


# ── T-N1..T-N6: negative fixtures ───────────────────────────────────────────

def test_tn1_p4_failure_triggers_rollback_and_parent_not_done(tmp_path):
    run_dir = str(tmp_path / "fail")
    ev = harness.build_funnel(run_dir, inject_failure="p4-build")
    assert ev["parent_done"] is False              # parent does NOT publish (F5)
    rb = json.load(open(os.path.join(run_dir, "logs", "funnel_rollback.json")))
    assert rb["triggered_by_stage"] == "p4-build"
    # Every autosaved page reverted byte-identical (live pointer unmoved).
    assert all(c["byte_identical"] for c in rb["baseline_md5_confirmed"])


def test_tn2_surviving_pending_qc_fails_r_copy(happy_run):
    run_dir, _ = happy_run
    p = os.path.join(run_dir, "working", "copy", "scent-bar-workshop", "copy.md")
    open(p, "w").write("# x\nstatus: PENDING-QC\n")
    res = {r.id: r.passed for r in rubrics.score_all(run_dir)}
    assert res["R-COPY"] is False


def test_tn3_deleted_persona_log_fails_r_persona_grounding(happy_run):
    run_dir, _ = happy_run
    os.remove(os.path.join(run_dir, "working", "funnels", "scent-bar-workshop", "persona-selection-log.md"))
    res = {r.id: r.passed for r in rubrics.score_all(run_dir)}
    assert res["R-PERSONA-GROUNDING"] is False


def test_tn4_injected_false_summary_fails_kanban_and_raises_contradiction(happy_run):
    run_dir, _ = happy_run
    raw = json.load(open(os.path.join(run_dir, "logs", "final-preview-verify.json")))
    raw["stages_complete"] = 5
    raw["overall_pass"] = False
    for i in (5, 6):
        raw["stages"][i]["passed"] = False
    json.dump(raw, open(os.path.join(run_dir, "logs", "final-preview-verify.json"), "w"))
    # summary still claims 7/7 — the injected lie. Rubric must catch it.
    res = {r.id: r.passed for r in rubrics.score_all(run_dir)}
    assert res["R-KANBAN-CORRECTNESS"] is False
    # And the harness consistency guard would have raised on write.
    summary = {"passed": 7, "overall_pass": True}
    with pytest.raises(AssertionError):
        harness._assert_summary_consistent(summary, raw["stages"])


def test_tn5_empty_evidence_fails_every_artifact_rubric(tmp_path):
    run_dir = str(tmp_path / "empty")
    os.makedirs(run_dir)
    res = {r.id: r.passed for r in rubrics.score_all(run_dir, cc_invariant_ok=True)}
    # Every artifact-backed rubric fails; only R-CC-SYNC (external invariant) can pass.
    for rid in ["R-COPY", "R-STRUCTURE", "R-PAGES", "R-FORMS", "R-PRODUCT",
                "R-EMAILS", "R-AUTOMATIONS", "R-PERSONA-GROUNDING", "R-KANBAN-CORRECTNESS"]:
        assert res[rid] is False, f"{rid} should fail on empty evidence"


def test_tn6_cc_invariant_failure_fails_r_cc_sync(happy_run):
    run_dir, _ = happy_run
    res = {r.id: r.passed for r in rubrics.score_all(run_dir, cc_invariant_ok=False)}
    assert res["R-CC-SYNC"] is False


# ── funnel_rollback idempotency (SOP-07 §7 final rule) ──────────────────────

def test_rollback_is_idempotent(tmp_path):
    ev_root = str(tmp_path / "logs")
    deleted = []
    inp = FunnelRollbackInputs(
        parent_task_id="epic", idempotency_key="k",
        triggered_by_stage="p5-automation", failed_task_id="p5",
        autosaved_pages=[{"funnel_id": "f", "page_id": "pg", "baseline": {"a": 1}, "current_version": 2}],
        ecosystem_objects=[{"type": "calendar", "id": "cal1", "qc_passed": False}],
        test_contact_id="contact-1",
    )
    live_objects = {("calendar", "cal1")}
    live_contacts = {"contact-1"}

    def deleter(t, i):
        live_objects.discard((t, i))
        deleted.append((t, i))
        return {"deleted": i}

    def cdeleter(i):
        live_contacts.discard(i)
        deleted.append(("contact", i))
        return {"deleted": i}

    common = dict(
        reverter=lambda req: req["baseline"],
        object_deleter=deleter,
        contact_deleter=cdeleter,
        object_exists=lambda t, i: (t, i) in live_objects,
        contact_exists=lambda i: i in live_contacts,
    )
    r1 = run_funnel_rollback(inp, ev_root, **common)
    first_deletes = list(deleted)
    r2 = run_funnel_rollback(inp, ev_root, **common)
    # Second run deletes NOTHING new (idempotent); record marks already_done.
    assert deleted == first_deletes, "rollback double-deleted on replay"
    assert any(o.get("already_done") for o in r2["objects_deleted"])
    assert r2["test_contact_deleted"] is True


def test_rollback_keeps_verified_objects(tmp_path):
    ev_root = str(tmp_path / "logs")
    deleted = []
    inp = FunnelRollbackInputs(
        parent_task_id="epic", idempotency_key="k",
        triggered_by_stage="p5", failed_task_id="p5",
        autosaved_pages=[],
        ecosystem_objects=[
            {"type": "calendar", "id": "keep", "qc_passed": True},     # verified -> keep
            {"type": "workflow", "id": "drop", "qc_passed": False},    # unverified -> delete
        ],
        test_contact_id=None,
    )
    run_funnel_rollback(
        inp, ev_root,
        object_deleter=lambda t, i: deleted.append((t, i)),
        object_exists=lambda t, i: True,
    )
    assert ("workflow", "drop") in deleted
    assert ("calendar", "keep") not in deleted


# ── T-PRE-1: index rebuild-then-assert (live; SKIP-with-reason if no provider) ──

def test_tpre1_index_rebuild_then_assert_provider_model_dim(tmp_path):
    """Run the canonical embedding indexer with --rebuild against a tiny corpus,
    then assert rowcount > 0 AND every embeddings row is provider='gemini',
    model='gemini-embedding-2', dim=3072.

    This is a REBUILD-THEN-ASSERT: it actually embeds. If no embedding provider
    is configured (clean CI, or a 402/network failure), it SKIPs with a reason —
    it never fakes a pass.
    """
    repo_root = os.path.dirname(os.path.dirname(HERE))
    su = os.path.join(repo_root, "shared-utils")
    if not os.path.isfile(os.path.join(su, "embedding_engine.py")):
        pytest.skip("embedding_engine.py not present in this checkout")
    if su not in sys.path:
        sys.path.insert(0, su)
    import sqlite3
    import importlib
    ee = importlib.import_module("embedding_engine")

    # Is an embedder actually available on this box? If not, SKIP honestly.
    try:
        prov, _client, model = ee.get_embedder()
    except SystemExit:
        pytest.skip("no embedding provider available (no GOOGLE_API_KEY/OPENAI_API_KEY) "
                    "— rebuild-then-assert SKIPPED, NOT faked")
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"embedder resolution failed: {e!r} — SKIPPED, NOT faked")
    if prov != "gemini" or model != ee.GEMINI_MODEL:
        pytest.skip(f"available embedder is {prov}/{model}, not gemini/{ee.GEMINI_MODEL} "
                    "— T-PRE-1 asserts the pinned gemini contract; SKIPPED")

    # Tiny throwaway corpus + DB so the rebuild is fast and side-effect free.
    personas = tmp_path / "personas"
    personas.mkdir()
    (personas / "sample-persona.md").write_text(
        "# Sample Persona\n\nValue-equation offer architecture for a high-ticket "
        "coaching program. Grand-slam offer stack and risk-reversal guarantee.\n",
        encoding="utf-8",
    )
    db_path = str(tmp_path / "idx.sqlite")
    try:
        rc = ee.cmd_index(rebuild=True, db_path=db_path, personas_dir=str(personas))
    except SystemExit:
        pytest.skip("embedder became unavailable mid-rebuild (e.g. 402) — SKIPPED, NOT faked")
    assert rc in (0, 2), f"indexer returned {rc}"

    conn = sqlite3.connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        if total == 0:
            pytest.skip("rebuild produced 0 rows (provider returned no vectors, e.g. quota) "
                        "— SKIPPED, NOT faked")
        rows = conn.execute(
            "SELECT DISTINCT provider, model, dim FROM embeddings").fetchall()
    finally:
        conn.close()

    assert total > 0, "rebuilt index has no rows"
    # EVERY row must carry the pinned provider/model/dim — no mixed/stale rows.
    assert rows == [("gemini", "gemini-embedding-2", 3072)], (
        f"index rows are not uniformly gemini/gemini-embedding-2/3072: {rows}")


# ── T-PRE-4: interview answers carry into KPI consumption (gap surfaced) ────────

def test_tpre4_interview_kpis_carry_verbatim_into_selector(tmp_path):
    """Interview-supplied company_kpis/owner_values must carry VERBATIM into the
    selector's KPI label consumption (the layer that scores persona fit), for BOTH
    config schemas. If the carry helper is missing, the test fails (surfaces the
    gap) rather than passing silently.
    """
    scripts = os.path.join(os.path.dirname(HERE), "scripts")
    selector_py = os.path.join(scripts, "persona-selector-v2.py")
    if not os.path.isfile(selector_py):
        pytest.fail("persona-selector-v2.py absent — interview->KPI carry path is "
                    "GONE (this is the gap T-PRE-4 must surface, not hide)")
    import importlib.util
    spec = importlib.util.spec_from_file_location("persona_selector_v2", selector_py)
    mod = importlib.util.module_from_spec(spec)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "_kpi_labels"), (
        "_kpi_labels helper missing — interview KPIs cannot carry into scoring")

    # Verbatim interview answers, in BOTH the list[str] and list[dict] shapes a
    # real interview-generated company-config.json carries.
    answer_a = "double deep-work hours in 90 days"
    answer_b = "90-day client retention above 85 percent"
    labels_schema_a = mod._kpi_labels([answer_a, answer_b])
    labels_schema_b = mod._kpi_labels(
        [{"name": answer_a, "target": "2x"}, {"name": answer_b, "target": "85%"}])

    # The interview answer text must appear VERBATIM in what the selector consumes.
    assert answer_a in labels_schema_a and answer_b in labels_schema_a
    assert answer_a in labels_schema_b and answer_b in labels_schema_b
    # And the KPI list must be NON-EMPTY (the spec's "KPIs non-empty" requirement).
    assert labels_schema_a and labels_schema_b


def test_tpre4_committed_live_run_surfaces_company_config_gap():
    """The committed FocusForge live run must HONESTLY surface the upstream
    interview->company_config KPI gap (not paper over it)."""
    surface = os.path.join(HERE, "evidence", "live-run-focusforge",
                           "logs", "T-PRE-4-surface.md")
    assert os.path.isfile(surface), "T-PRE-4-surface.md missing from committed evidence"
    txt = open(surface, encoding="utf-8").read().lower()
    assert "company-config" in txt or "company_config" in txt
    assert "gap" in txt and ("neutral" in txt or "0.6" in txt), (
        "T-PRE-4 evidence must surface the degraded/neutral KPI gap honestly")


# ── T-N5: empty persona index BLOCKS the pipeline (fail-closed) ────────────────

def test_tn5_empty_index_blocks_pipeline_at_persona_grounding_gate(tmp_path):
    """An EMPTY persona index means the selector had no corpus to ground against.
    The pipeline must BLOCK (fail-closed) at the persona-grounding gate — it must
    NOT proceed to build ungrounded copy/pages."""
    run_dir = str(tmp_path / "n5")
    with pytest.raises(rubrics.PersonaGroundingBlocked):
        harness.build_funnel(run_dir, inject_empty_index=True)
    # Fail-closed proof: NO downstream artifacts were built.
    assert not os.path.exists(
        os.path.join(run_dir, "working", "copy", "scent-bar-workshop", "copy.md"))
    assert not os.path.exists(
        os.path.join(run_dir, "ecosystem", "workflow.json"))


def test_tn5_persona_grounding_gate_passes_on_grounded_happy_run(happy_run):
    run_dir, _ = happy_run
    res = rubrics.persona_grounding_gate(run_dir)
    assert res["ok"] is True
    assert res["persona"] == "hormozi-100m-offers"


def test_tn5_gate_blocks_when_selector_marker_absent(happy_run):
    """Even with a non-empty index, a selection-log with NO selector_ran marker
    means no real selection happened — the gate must fail-closed."""
    run_dir, _ = happy_run
    p = os.path.join(run_dir, "working", "funnels", "scent-bar-workshop",
                     "persona-selection-log.md")
    open(p, "w").write("# log\n- selected_persona: hormozi-100m-offers\n")  # no selector_ran
    res = rubrics.persona_grounding_gate(run_dir)
    assert res["ok"] is False


# ── Graduation: the rubric scorer computes a MAGNITUDE, not a constant ─────────

def test_rubric_pages_is_graduated_not_constant(happy_run):
    """Dropping 1 of 3 pages' http-200 must move R-PAGES to a value strictly
    BETWEEN 0 and the full score — a constant scorer cannot do this."""
    run_dir, _ = happy_run
    full = {r.id: r.score for r in rubrics.score_all(run_dir)}["R-PAGES"]
    bp = os.path.join(run_dir, "working", "funnels", "scent-bar-workshop", "build-result.json")
    b = json.load(open(bp))
    b["pages"][0]["preview_http"] = 500
    b["pages"][0]["content_url_http"] = 500
    json.dump(b, open(bp, "w"))
    degraded = {r.id: r.score for r in rubrics.score_all(run_dir)}["R-PAGES"]
    assert 0 < degraded < full, f"R-PAGES not graduated: full={full} degraded={degraded}"


def test_rubric_emails_score_scales_with_email_count(happy_run):
    run_dir, _ = happy_run
    ep = os.path.join(run_dir, "working", "email", "scent-bar-workshop", "email-sequence.json")
    full = {r.id: r.score for r in rubrics.score_all(run_dir)}["R-EMAILS"]
    e = json.load(open(ep))
    e["emails"] = e["emails"][:2]            # 5 -> 2
    json.dump(e, open(ep, "w"))
    degraded = {r.id: r.score for r in rubrics.score_all(run_dir)}["R-EMAILS"]
    assert degraded < full, f"R-EMAILS did not scale with count: {full} vs {degraded}"


def test_rubric_forms_partial_evidence_scores_between_0_and_full(happy_run):
    run_dir, _ = happy_run
    cp = os.path.join(run_dir, "ecosystem", "contact-test.json")
    full = {r.id: r.score for r in rubrics.score_all(run_dir)}["R-FORMS"]
    c = json.load(open(cp))
    # Strip the routed-tags sub-check only (keep the form-present + 201 signals).
    c["tags_confirmed"] = False
    c["tags_on_contact"] = []
    c.pop("qc_passed", None)
    c["form_capture_http"] = 201
    json.dump(c, open(cp, "w"))
    degraded = {r.id: r.score for r in rubrics.score_all(run_dir)}["R-FORMS"]
    assert 0 < degraded < full, f"R-FORMS not partial-graded: full={full} degraded={degraded}"


def test_rubric_structure_hard_miss_on_funnel_type(happy_run):
    """A load-bearing sub-check (funnel_type, weight 3) earning 0 must FAIL the
    rubric outright, even though the remaining sub-checks would average > 8.5."""
    run_dir, _ = happy_run
    sp = os.path.join(run_dir, "working", "funnels", "scent-bar-workshop", "funnel-spec.json")
    s = json.load(open(sp))
    s.pop("funnel_type", None)
    json.dump(s, open(sp, "w"))
    res = {r.id: r for r in rubrics.score_all(run_dir)}["R-STRUCTURE"]
    assert res.passed is False, "hard-miss gate did not fire on missing funnel_type"


def test_rubric_scores_are_not_all_one_constant(happy_run):
    """Across a happy run + a degraded run, the rubric scores must take MORE THAN
    ONE distinct value — proving they are computed, not a single hardcoded number."""
    run_dir, _ = happy_run
    full_scores = [r.score for r in rubrics.score_all(run_dir)]
    # Degrade one rubric and rescore.
    ep = os.path.join(run_dir, "working", "email", "scent-bar-workshop", "email-sequence.json")
    e = json.load(open(ep)); e["emails"] = e["emails"][:1]; json.dump(e, open(ep, "w"))
    degraded_scores = [r.score for r in rubrics.score_all(run_dir)]
    assert len(set(full_scores + degraded_scores)) > 1


# ── committed live-run: ONE documented environmental residual, honestly scored ──

def test_committed_live_run_is_10of11_with_persona_grounding_residual():
    """The committed FocusForge live run must score EXACTLY one documented
    environmental residual — R-PERSONA-GROUNDING below 8.5 — with all 10 OTHER
    rubrics at or above 8.5 and an overall mean well above 8.5. This locks the
    honest finish: the degraded grounding (selector Layers 1-4 fell to neutral-0.6
    from an OpenRouter 402 + a fixture box with no company-config) is DOCKED, not
    faked to a pass, and no OTHER rubric silently regressed below the floor."""
    run_dir = os.path.join(HERE, "evidence", "live-run-focusforge")
    results = {r.id: r for r in rubrics.score_all(run_dir)}
    below = [rid for rid, r in results.items() if not r.passed]
    assert below == ["R-PERSONA-GROUNDING"], (
        f"expected ONLY R-PERSONA-GROUNDING below {rubrics.THRESHOLD}, got {below}")
    g = results["R-PERSONA-GROUNDING"]
    assert g.score < rubrics.THRESHOLD, "grounding residual must be genuinely below the floor"
    # The dock comes from the degraded selector strength, not a missing persona name.
    assert "neutral" in g.raw_signal.lower() or "degraded" in g.raw_signal.lower()
    mean = round(sum(r.score for r in results.values()) / len(results), 2)
    assert mean >= rubrics.THRESHOLD, f"overall mean {mean} should clear the floor"


def test_allow_documented_residual_gate_is_honest():
    """`--allow-documented-residual` must (a) PASS the gate when the named rubric is
    the sole sub-threshold rubric, (b) FAIL when no allowance is given, and (c) FAIL
    a STALE/bogus allowance that names a PASSING rubric — so it can never mask a
    regression."""
    scorer = os.path.join(HERE, "funnel_rubrics.py")
    run_dir = os.path.join(HERE, "evidence", "live-run-focusforge")
    base = [sys.executable, scorer, "--run-dir", run_dir, "--gate"]

    # (b) no allowance → fail
    r_none = subprocess.run(base, capture_output=True, text=True)
    assert r_none.returncode == 1, "gate must FAIL the degraded live run with no allowance"
    assert "RUBRIC GATE FAILED" in r_none.stderr

    # (a) named residual allowed → pass, residual surfaced loudly
    r_ok = subprocess.run(base + ["--allow-documented-residual", "R-PERSONA-GROUNDING"],
                          capture_output=True, text=True)
    assert r_ok.returncode == 0, f"gate must PASS with the documented residual allowed:\n{r_ok.stderr}"
    assert "DOCUMENTED ENVIRONMENTAL RESIDUAL" in r_ok.stderr

    # (c) bogus allowance (a passing rubric) → fail STALE
    r_bogus = subprocess.run(base + ["--allow-documented-residual", "R-COPY"],
                             capture_output=True, text=True)
    assert r_bogus.returncode == 1, "a stale allowance naming a passing rubric must FAIL"
    assert "STALE" in r_bogus.stderr
