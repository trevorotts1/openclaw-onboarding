"""PRES-031 -- scoped persona context + versioned bundle cache + section
selection replacing the 8000-char slice.

QC-PRES-031:
  1. Two clients (different audiences) + two presentations for one client ->
     correctly scoped contexts; no cross-run cached bundle reuse.
  2. Bundle >8000 chars with a required rule near the end -> complete rule
     delivered, or preflight explicitly restructures; never silent cut.
  3. Owner-named voice intact; execution + audience voice independently
     represented with recorded IDs/hashes.
  4. Teaching slides checked for covert pitches; sales/VSL use approved
     offer claims without invented proof.

stdlib + pytest + tmp_path only. No network, no selector (fixture seam).
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
sys.path.insert(0, str(_SCRIPTS))

from presentation_job import persona_context as pc

def _find_golden_sp() -> Path:
    """Locate the golden-quest sp_intake.json from scripts/ or repo root."""
    cands = [
        _SCRIPTS.parent.parent / "51-signature-presentation" / "examples"
        / "golden-quest" / "sp_intake.json",
        _SCRIPTS / "51-signature-presentation" / "examples"
        / "golden-quest" / "sp_intake.json",
    ]
    here = _SCRIPTS
    for anc in [here] + list(here.parents):
        c = (anc / "51-signature-presentation" / "examples"
             / "golden-quest" / "sp_intake.json")
        if c.is_file():
            return c
    for c in cands:
        if c.is_file():
            return c
    raise FileNotFoundError(
        "golden-quest sp_intake.json not found from %s" % _SCRIPTS)


GOLDEN_SP = _find_golden_sp()


def _run_with_intake(tmp_path, name, sp_obj, intake_obj):
    rd = tmp_path / name
    c = rd / "working" / "copy"
    c.mkdir(parents=True)
    (c / "sp_intake.json").write_text(json.dumps(sp_obj))
    (c / "intake.json").write_text(json.dumps(intake_obj))
    (rd / "state.json").write_text(json.dumps({
        "schema_version": 1, "job_id": "t", "intake": {}, "phases": []}))
    return rd


def _base_sp():
    return json.loads(GOLDEN_SP.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# QC-1: cross-client + cross-presentation isolation.
# ---------------------------------------------------------------------------

def test_qc1_two_clients_two_presentations_isolated(tmp_path):
    sp_a = _base_sp()
    rd_a = _run_with_intake(tmp_path, "run-a", sp_a,
                            {"client_name": "Acme", "deck_slug": "deck-one",
                             "requester_chat_id": "1"})
    sp_b = _base_sp()
    sp_b["answers"] = dict(sp_b["answers"])
    sp_b["answers"]["q3"] = "enterprise CTOs at Fortune 500 firms"
    rd_b = _run_with_intake(tmp_path, "run-b", sp_b,
                            {"client_name": "Globex",
                             "deck_slug": "deck-two",
                             "requester_chat_id": "2"})
    rd_c = _run_with_intake(tmp_path, "run-c", _base_sp(),
                            {"client_name": "Acme", "deck_slug": "deck-two",
                             "requester_chat_id": "1"})
    ca = pc.build_persona_context(rd_a, "P4-COPY")
    cb = pc.build_persona_context(rd_b, "P4-COPY")
    cc = pc.build_persona_context(rd_c, "P4-COPY")
    assert ca["client_id"] != cb["client_id"]
    assert ca["audience"]["value"] != cb["audience"]["value"]
    assert pc.cache_key_for(ca) != pc.cache_key_for(cb)
    assert pc.cache_key_for(ca) != pc.cache_key_for(cc), \
        "two presentations for one client must not share a bundle key"
    assert ca["context_hash"] != cb["context_hash"] != cc["context_hash"]


def test_qc1_no_cross_run_cache_reuse(tmp_path):
    rd_a = _run_with_intake(tmp_path, "run-a", _base_sp(),
                            {"client_name": "Acme", "deck_slug": "deck-one",
                             "requester_chat_id": "1"})
    rd_b = _run_with_intake(tmp_path, "run-b", _base_sp(),
                            {"client_name": "Globex",
                             "deck_slug": "deck-two",
                             "requester_chat_id": "2"})
    ca = pc.build_persona_context(rd_a, "P4-COPY")
    bundle = {"blend_directive": "STYLE-INSPIRED, NEVER IMPERSONATION. "
                                 "Write in second person. no-pitch.",
              "voice": {"a": 1}, "resolved_audience": {"label": "x"},
              "rationale": {"why": "y"}}
    pc.store_bundle(rd_a, ca, bundle)
    cb = pc.build_persona_context(rd_b, "P4-COPY")
    assert pc.lookup_bundle(rd_b, cb) is None
    assert pc.lookup_bundle(rd_a, ca) == bundle


# ---------------------------------------------------------------------------
# QC-2: >8000-char bundle, required rule near the end.
# ---------------------------------------------------------------------------

def _big_bundle():
    return {
        "blend_directive":
            "STYLE-INSPIRED, NEVER IMPERSONATION. Write in second person. "
            + "x" * 9000
            + " Final binding rule: always close in second person with a "
              "no-pitch teaching boundary.",
        "voice": {"audience_persona": {"id": "a"},
                  "topic_persona": {"id": "t"}},
        "resolved_audience": {"label": "founders"},
        "rationale": {"why": "because"},
        "task_personas": [{"slot": "hook"}],
    }


def test_qc2_long_bundle_complete_rule_delivered(tmp_path):
    sel = pc.select_bundle_sections(_big_bundle(), phase_id="P4-COPY",
                                    task_mode="copy")
    assert sel["complete"] is True
    assert "no-pitch" in sel["text"] and "second person" in sel["text"]
    assert "Final binding rule" in sel["text"]
    assert len(sel["text"]) > 8000  # the old slice would have cut it


def test_qc2_dropped_governance_fails_closed(tmp_path):
    bundle = {"blend_directive": "Write nicely. " + "x" * 500,
              "voice": {"a": 1}, "resolved_audience": {"label": "x"},
              "rationale": {"why": "y"}}
    sel = pc.select_bundle_sections(bundle, phase_id="P4-COPY",
                                    task_mode="copy")
    assert sel["complete"] is False
    assert "STYLE-INSPIRED, NEVER IMPERSONATION" in sel["missing_markers"]


def test_qc2_compose_prompt_raises_not_truncates(tmp_path, monkeypatch):
    from presentation_job import dispatcher as disp
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "state.json").write_text(json.dumps({
        "schema_version": 1, "phases": [
            {"id": "P4-COPY", "persona_bundle": {
                "blend_directive": "Write nicely.",
                "voice": {"a": 1}, "resolved_audience": {"label": "x"},
                "rationale": {"why": "y"}}}]}))
    monkeypatch.setattr(disp, "load_role_context",
                        lambda *a, **k: "ROLE SOP")
    monkeypatch.setattr(disp, "gather_upstream_context",
                        lambda *a, **k: "UPSTREAM")
    import pytest as _pt
    with _pt.raises(Exception, match="AF-PERSONA-GOVERNANCE"):
        disp.compose_prompt(
            phase_id="P4-COPY", owning_role="copywriter-presentations",
            dept_root=tmp_path, run_dir=rd, order={}, attempt=1,
            prior_reasons=None)


# ---------------------------------------------------------------------------
# QC-3: owner voice intact, execution vs audience voice separate.
# ---------------------------------------------------------------------------

def test_qc3_owner_voice_preserved_and_separate(tmp_path):
    rd = _run_with_intake(tmp_path, "run", _base_sp(),
                          {"client_name": "Acme", "deck_slug": "deck-one",
                           "requester_chat_id": "1"})
    ctx = pc.build_persona_context(rd, "P4-COPY")
    assert ctx["owner_voice"]["value"], "golden quest names an owner voice"
    assert ctx["execution_persona"]["scope"] == "department"
    assert ctx["client_voice"]["scope"] == "client-audience"
    assert ctx["execution_persona"] != ctx["client_voice"]
    assert ctx["client_voice"]["owner_voice"] == ctx["owner_voice"]["value"]
    # IDs + hashes recorded.
    assert ctx["client_id"] and ctx["presentation_id"]
    assert ctx["context_hash"]


# ---------------------------------------------------------------------------
# QC-4: doctrine checks.
# ---------------------------------------------------------------------------

def test_qc4_covert_pitch_in_teaching_fails():
    ctx = {"framework": "transformational-teaching",
           "offer": {"products": ["The Called Collective"]}}
    bad = pc.check_no_covert_pitch(
        "In this teaching unit, buy now for a limited time discount price!",
        "P-SP-P3-HYGIENE", ctx)
    assert bad["ok"] is False
    good = pc.check_no_covert_pitch(
        "Name the ache you carry and walk before you are ready.",
        "P-SP-P3-HYGIENE", ctx)
    assert good["ok"] is True


def test_qc4_sales_page_uses_approved_offer_claims():
    ctx = {"framework": "offer-sales-page",
           "offer": {"products": ["The Called Collective"]}}
    invented = pc.check_offer_claims(
        "Our clients earned fortunes with testimonials and guaranteed "
        "results!",
        {"offer": {"products": ["The Called Collective"]}})
    assert invented["ok"] is False
    anchored = pc.check_offer_claims(
        "Join The Called Collective, our twelve-week group mastermind.",
        {"offer": {"products": ["The Called Collective"]}})
    assert anchored["ok"] is True
