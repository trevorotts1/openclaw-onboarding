"""PRES-053 — PersonaService hermetic + scoping + closure tests.

Stdlib + pytest only. Hermetic (SCORING_MODE=heuristic, use_llm=False,
record=False into scoped storage). No network, no live DB, no operator
roots. Real packaged resources (99 blueprints) — not mocks.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
sys.path.insert(0, str(_SCRIPTS))

os.environ["SCORING_MODE"] = "heuristic"

from presentation_job.persona_service import (  # noqa: E402
    FileStorage,
    NullStorage,
    PersonaContext,
    PersonaService,
)
from presentation_job.persona_service.bundle import (  # noqa: E402
    governance_excerpt,
    required_texts_for_receipt,
    verify_bundle_integrity,
    verify_consumption,
)
from presentation_job.persona_service.catalog import PackagedCatalog  # noqa: E402
from presentation_job.persona_service.policy import (  # noqa: E402
    NARRATIVE_PHASE_FOR,
    all_policy_phases,
    policy_for_phase,
    unresolved_phases,
)

RESOURCES = Path(_SCRIPTS, "presentation_job", "persona_service", "resources")


@pytest.fixture()
def storage_dir(tmp_path):
    return tmp_path / "store"


@pytest.fixture()
def service(storage_dir):
    return PersonaService(RESOURCES, storage=FileStorage(storage_dir))


def _ctx(**kw):
    base = dict(company_id="acme-co", presentation_id="deck-q3",
                run_id="run-1", audience="founders building courses",
                topic="offers", offer="buy the course",
                role="slide-copywriter", phase="P4-COPY", hermetic=True)
    base.update(kw)
    return PersonaContext(**base)


# ---------------------------------------------------------------------------
# Catalog closure
# ---------------------------------------------------------------------------
def test_catalog_closure_no_missing_blueprints():
    cat = PackagedCatalog(RESOURCES / "personas")
    ok, problems = cat.validate_closure()
    assert ok, problems
    assert len(cat.persona_ids()) == 99
    assert cat.missing_blueprints() == []
    assert len(cat.resource_hashes()) == 101  # catalog + map + 99 blueprints


def test_missing_blueprint_fails_doctor(tmp_path):
    import shutil
    broken = tmp_path / "res-broken"
    shutil.copytree(RESOURCES, broken)
    # Remove one blueprint the catalog references.
    bps = sorted((broken / "personas" / "personas").glob("*/persona-blueprint.md"))
    assert bps
    bps[0].unlink()
    svc = PersonaService(broken, storage=NullStorage())
    report = svc.doctor()
    assert report["ok"] is False
    assert any("missing blueprint" in p for p in report["problems"])


def test_doctor_ok_on_package(service):
    report = service.doctor()
    assert report["ok"] is True, report["problems"]


# ---------------------------------------------------------------------------
# Governance excerpt parity with the frozen seam
# ---------------------------------------------------------------------------
def test_governance_excerpts_match_frozen_seam_all_personas():
    sys.path.insert(0, str(Path(_SCRIPTS).parents[4] / "shared-utils"))
    from persona_for_job import section4_excerpt as frozen_excerpt
    cat = PackagedCatalog(RESOURCES / "personas")
    bad = [pid for pid in cat.persona_ids()
           if governance_excerpt(cat, pid) != frozen_excerpt(pid)]
    assert bad == []


# ---------------------------------------------------------------------------
# Narrative-phase parity (frozen persona.BLEND_PHASE_FOR + Skill51 PHASES)
# ---------------------------------------------------------------------------
def test_narrative_phase_parity():
    from presentation_job import persona as frozen_persona
    import importlib.util
    repo = Path(_SCRIPTS).parents[4]
    spec = importlib.util.spec_from_file_location(
        "bvg_pres053", str(repo / "51-signature-presentation" / "scripts"
                            / "blend_voice_governance.py"))
    bvg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bvg)
    assert set(frozen_persona.BLEND_PHASE_FOR.values()) == set(bvg.PHASES)
    assert set(NARRATIVE_PHASE_FOR) == set(frozen_persona.BLEND_PHASE_FOR)
    assert set(NARRATIVE_PHASE_FOR.values()) == set(bvg.PHASES)


# ---------------------------------------------------------------------------
# Policy coverage: every manifest phase has an execution specialist
# ---------------------------------------------------------------------------
def test_policy_covers_all_manifest_phases():
    manifest = json.loads(
        (Path(_SCRIPTS).parents[4]
         / "universal-sops" / "presentation-slide-craft"
         / "PIPELINE-MANIFEST.json").read_text(encoding="utf-8"))
    phase_ids = [p["id"] for p in manifest["phases"]]
    assert len(phase_ids) == 62
    assert unresolved_phases(phase_ids) == []
    kinds = {policy_for_phase(p)["kind"] for p in phase_ids}
    assert {"governed-blend", "execution-only", "qc-independent",
            "human-gate"} <= kinds


# ---------------------------------------------------------------------------
# Acceptance 1: two companies + two presentations scope correctly
# ---------------------------------------------------------------------------
def test_two_companies_two_presentations_scoped(service):
    r1 = service.resolve(_ctx())
    r2 = service.resolve(_ctx(
        company_id="other-co", presentation_id="deck-x", run_id="run-9",
        audience="pastors", topic="stewardship", offer="give"))
    r3 = service.resolve(_ctx(presentation_id="deck-q4", run_id="run-2"))
    assert r1.context_hash != r2.context_hash != r3.context_hash
    assert r1.context_hash != r3.context_hash  # run/presentation in hash
    assert r1.voice_persona_id  # governed voice resolved
    assert r2.voice_persona_id
    # Scoped persistence: one receipt per company/presentation/run.
    store = service.storage.root
    assert (store / "acme-co" / "deck-q3" / "run-1" / "receipt-P4-COPY.json").is_file()
    assert (store / "other-co" / "deck-x" / "run-9" / "receipt-P4-COPY.json").is_file()
    assert (store / "acme-co" / "deck-q4" / "run-2" / "receipt-P4-COPY.json").is_file()
    # No cross-company read: other-co has no acme receipt.
    assert not (store / "other-co" / "deck-q3").exists()


def test_resume_reuses_identical_context_with_rationale(service):
    first = service.resolve(_ctx())
    hit = service.cached_receipt(_ctx())
    assert hit is not None
    assert hit.voice_persona_id == first.voice_persona_id
    assert hit.topic_persona_id == first.topic_persona_id
    assert hit.rationale  # per-part + blend rationale survives resume
    assert "collapse" in hit.rationale


def test_context_change_invalidates_cache(service):
    service.resolve(_ctx())
    stale = service.cached_receipt(_ctx(topic="webinars"))
    assert stale is None


def test_content_change_invalidates_cache(service, storage_dir, tmp_path):
    svc = PersonaService(RESOURCES, storage=FileStorage(storage_dir))
    first = svc.resolve(_ctx())
    assert svc.cached_receipt(_ctx()) is not None
    # Simulate a blueprint change by pointing at a copied resource tree
    # with one altered blueprint.
    import shutil
    altered = tmp_path / "res-altered"
    shutil.copytree(RESOURCES, altered)
    bps = sorted((altered / "personas" / "personas").glob("*/persona-blueprint.md"))
    bps[0].write_text(bps[0].read_text(encoding="utf-8") + "\n<!-- rev -->\n",
                      encoding="utf-8")
    svc2 = PersonaService(altered, storage=FileStorage(storage_dir))
    assert svc2.catalog.content_version() != svc.catalog.content_version()
    assert svc2.cached_receipt(_ctx()) is None


# ---------------------------------------------------------------------------
# Execution-vs-client-voice separation + QC independence + human gate
# ---------------------------------------------------------------------------
def test_execution_specialist_differs_from_client_voice_shape(service):
    receipt = service.resolve(_ctx())
    assert receipt.policy["kind"] == "governed-blend"
    assert receipt.policy["execution_specialist"] == "slide-copywriter"
    assert receipt.voice_persona_id  # client-facing voice resolved
    assert receipt.blend_directive  # directive present


def test_qc_reviewer_differs_from_producer(service):
    producer = service.resolve(_ctx())
    qc = service.resolve(_ctx(phase="P1Q-COPY-QC"))
    assert qc.policy["kind"] == "qc-independent"
    assert qc.voice_persona_id != producer.voice_persona_id
    assert "qc_independence" in (qc.rationale or {})


def test_human_gate_resolves_nothing(service):
    receipt = service.resolve(_ctx(phase="P-STYLE-PICK"))
    assert receipt.policy["kind"] == "human-gate"
    assert receipt.no_persona_required is True
    assert receipt.voice_persona_id == ""


def test_client_choice_honored_verbatim(service):
    receipt = service.resolve(_ctx(client_persona_id="td-jakes-instinct",
                                   client_persona_source="client-choice"))
    assert receipt.voice_persona_id == "td-jakes-instinct"


# ---------------------------------------------------------------------------
# Acceptance 2 pieces: integrity, fake-semantic, omitted-text QC-fail
# ---------------------------------------------------------------------------
def test_receipt_integrity_passes(service):
    receipt = service.resolve(_ctx())
    assert verify_bundle_integrity(receipt) == []


def test_fake_semantic_claim_fails_qc(service):
    import copy
    receipt = copy.copy(service.resolve(_ctx()))
    receipt.semantic_claimed = True
    receipt.semantic_evidence = ""
    problems = verify_bundle_integrity(receipt)
    assert any("semantic" in p for p in problems)


def test_consumed_text_passes_omitted_text_fails(service):
    receipt = service.resolve(_ctx())
    cat = PackagedCatalog(RESOURCES / "personas")
    required = required_texts_for_receipt(receipt, cat)
    assert set(required) >= {"voice", "topic", "blend_directive"}
    assert all(v.strip() for v in required.values())  # mandatory bytes loaded
    rendered = " ".join(required.values())
    assert verify_consumption(receipt, rendered, cat) == []
    unrelated = ("unrelated filler about plumbing fixtures with no persona "
                 "substance whatsoever, repeated many times over and over")
    problems = verify_consumption(receipt, unrelated, cat)
    assert any("not consumed" in p for p in problems)


# ---------------------------------------------------------------------------
# Hermetic closure: no live roots touched
# ---------------------------------------------------------------------------
def test_hermetic_run_writes_nothing_outside_scoped_storage(
        service, storage_dir, tmp_path, monkeypatch):
    home = tmp_path / "fakehome"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ("OPENCLAW_PLATFORM", "OPENCLAW_COMPANY_CONFIG",
                "OPENCLAW_COMPANY_SLUG", "OPENCLAW_AUDIENCE",
                "OPENCLAW_PERSONA_CATEGORIES", "OPENCLAW_PERSONA_MATCH_SCORE_LOG",
                "PERSONA_SELECTION_LOG_PATH", "DASHBOARD_DB_PATH",
                "DATABASE_PATH", "OPENCLAW_TASK_ID"):
        monkeypatch.delenv(var, raising=False)
    service.resolve(_ctx())
    assert not (home / ".openclaw").exists()
    assert list(storage_dir.rglob("receipt-P4-COPY.json"))
