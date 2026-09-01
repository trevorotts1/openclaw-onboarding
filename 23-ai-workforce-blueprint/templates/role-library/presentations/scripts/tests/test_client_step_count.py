"""Tests for B2 (MASTER-WORK-ORDER-20260818 / FABLE-TRUTH.md SS1) -- the
CLIENT-FACING step count in run_signature_deck.py.

Ground truth this file pins (FABLE-TRUTH SS1 / MASTER-WORK-ORDER B2):
  * 36 is the enforced, machine-walked phase count in PIPELINE-MANIFEST.json --
    unchanged, always, everywhere it is an ENFORCEMENT surface (`phases`,
    declared_plan.json's `steps`/`total`, the attestation chain, phase_verifiers'
    registry, execution_plan.py's DAG).
  * 31 phases do real work on a standard from-scratch deck (5 conditional
    pass-throughs: P-CONVERTER + the four P-SP-* signature-only phases).
    Wave C unit C1 (manifest_version 51) added 4 more conditional
    pass-throughs (P-U-SALES-BUILD/P-U-CHECKOUT-BUILD/P-U-FORM-CHECKOUT/
    P-U-VSL-BUILD, gated on the upsell intake flags) -- none of these
    fixtures set those flags, so all four stay client-visible (fail-safe:
    unknown widens), making the real counts below 35/39/36/40.
  * 35 on a signature deck (only P-CONVERTER is conditional there).
  * 32 on a content-conversion deck (only the four P-SP-* phases are
    conditional there).
  * P-SP-CLAIM is the routing gate and runs for real on EVERY deck -- it must
    NEVER be filtered out of the client-facing count.
  * What changes is ONLY the client-facing PRESENTATION of the count
    (declare_plan()'s outbound message + emit_client_report()'s "Step k of N"
    wording) -- never `phases`, the runner's walk, the DAG, or the verifier
    registry, and never declared_plan.json's `steps`/`total` fields (the
    contract prove-deck.py's AF-PROCESS-INTEGRITY certificate cross-checks
    1:1 against the attestation chain).

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_executor_dispatch.py, test_gates.py, etc.).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import run_signature_deck as rsd  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _manifest_phases() -> list:
    return rsd.load_manifest()["phases"]


def _run_dir(tmp_path, deck_type=None, creation_mode=None, no_intake=False) -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    if not no_intake:
        obj = {}
        if deck_type is not None:
            obj["deck_type"] = deck_type
        if creation_mode is not None:
            obj["creation_mode"] = creation_mode
        (rd / "working" / "copy" / "intake.json").write_text(json.dumps(obj))
    return rd


_SP_ONLY = ("P-SP-INTAKE", "P-SP-INTAKE-TRACE", "P-SP-STRUCTURE", "P-SP-P3-HYGIENE")


# ---------------------------------------------------------------------------
# 0. The enforced 36 -- proof it is untouched by this unit.
# ---------------------------------------------------------------------------
class TestEnforcedCountUnchanged:
    def test_manifest_has_36_phases(self):
        phases = _manifest_phases()
        assert len(phases) == 55  # 36 + C1's 4 BUILD + 15 DESIGN-OPUS P-U phases (merged 2026-09-01, manifest v54+)

    def test_client_visible_phases_never_mutates_input(self, tmp_path):
        phases = _manifest_phases()
        before = [p["id"] for p in phases]
        rd = _run_dir(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        rsd._client_visible_phases(rd, phases)
        after = [p["id"] for p in phases]
        assert before == after, "the raw manifest phase list must never be filtered in place"

    def test_raw_phase_index_still_walks_all_36(self, tmp_path):
        """_phase_index (the pre-existing, non-client-filtered helper) must keep
        returning positions against the FULL 36 -- nothing about the
        enforcement walk changed, only the NEW client-facing twin filters."""
        phases = _manifest_phases()
        k, n = rsd._phase_index("P-CONVERTER", phases)
        assert n == 55
        assert k == 1  # P-CONVERTER is order -1, the lowest-order phase

    def test_verifier_registry_covers_all_36(self):
        """Independent proof (not just phases[]) that the 36-phase enforcement
        surface phase_verifiers.py registers is untouched by this unit."""
        import phase_verifiers
        ids = {p["id"] for p in _manifest_phases()}
        registered = set(phase_verifiers.PHASE_VERIFIERS.keys())
        missing = ids - registered
        assert not missing, f"phase_verifiers.py is missing verifiers for: {sorted(missing)}"


# ---------------------------------------------------------------------------
# 1. _client_visible_phases -- the three named deck types + fail-safe unknown.
# ---------------------------------------------------------------------------
class TestClientVisibleCounts:
    def test_standard_from_scratch_is_31(self, tmp_path):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        visible = rsd._client_visible_phases(rd, phases)
        assert len(visible) == 44  # 31 base + 13 P-U run-by-default (webinar; merged 2026-09-01)
        ids = {p["id"] for p in visible}
        assert "P-CONVERTER" not in ids
        for pid in _SP_ONLY:
            assert pid not in ids

    def test_signature_is_35(self, tmp_path):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type="signature_presentation", creation_mode="from_scratch")
        visible = rsd._client_visible_phases(rd, phases)
        assert len(visible) == 48  # 35 base + 13 P-U (signature; SP 4 kept, converter filtered)
        ids = {p["id"] for p in visible}
        assert "P-CONVERTER" not in ids
        for pid in _SP_ONLY:
            assert pid in ids

    def test_content_conversion_is_32(self, tmp_path):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type="webinar", creation_mode="content_personal")
        visible = rsd._client_visible_phases(rd, phases)
        assert len(visible) == 45  # 32 + 13 P-U phases (merged 2026-09-01)
        ids = {p["id"] for p in visible}
        assert "P-CONVERTER" in ids
        for pid in _SP_ONLY:
            assert pid not in ids

    def test_content_conversion_general_mode_also_32(self, tmp_path):
        """Both content-first creation_mode values (content_personal AND
        content_general) route P-CONVERTER in -- not just one of them."""
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type="webinar", creation_mode="content_general")
        visible = rsd._client_visible_phases(rd, phases)
        assert len(visible) == 45  # 32 + 13 P-U phases (merged 2026-09-01)

    def test_unknown_intake_fails_safe_to_full_36(self, tmp_path):
        """No intake.json at all -- both signals unknown -- must NEVER shrink
        below the honest superset."""
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, no_intake=True)
        visible = rsd._client_visible_phases(rd, phases)
        assert len(visible) == 55

    def test_empty_intake_object_fails_safe_to_full_36(self, tmp_path):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path)  # writes {} -- both fields absent
        visible = rsd._client_visible_phases(rd, phases)
        assert len(visible) == 55

    def test_deck_type_known_but_creation_mode_unknown_only_filters_sp(self, tmp_path):
        """Partial knowledge filters ONLY the signal that is actually known --
        the other signal's fail-safe default must not be dragged down with it."""
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type="webinar", creation_mode=None)
        visible = rsd._client_visible_phases(rd, phases)
        ids = {p["id"] for p in visible}
        assert "P-CONVERTER" in ids  # creation_mode unknown -> not filtered
        for pid in _SP_ONLY:
            assert pid not in ids  # deck_type positively known non-signature -> filtered

    def test_sp_claim_never_filtered_on_any_deck_type(self, tmp_path):
        phases = _manifest_phases()
        for dt, cm in (("webinar", "from_scratch"),
                       ("signature_presentation", "from_scratch"),
                       ("webinar", "content_personal"),
                       (None, None)):
            rd = tmp_path / f"r-{dt}-{cm}"
            rd.mkdir()
            (rd / "working" / "copy").mkdir(parents=True)
            obj = {}
            if dt is not None:
                obj["deck_type"] = dt
            if cm is not None:
                obj["creation_mode"] = cm
            (rd / "working" / "copy" / "intake.json").write_text(json.dumps(obj))
            ids = {p["id"] for p in rsd._client_visible_phases(rd, phases)}
            assert "P-SP-CLAIM" in ids, f"P-SP-CLAIM filtered for deck_type={dt!r} creation_mode={cm!r}"

    def test_unreadable_intake_json_fails_safe(self, tmp_path):
        phases = _manifest_phases()
        rd = tmp_path / "broken"
        (rd / "working" / "copy").mkdir(parents=True)
        (rd / "working" / "copy" / "intake.json").write_text("{not valid json")
        visible = rsd._client_visible_phases(rd, phases)
        assert len(visible) == 55


# ---------------------------------------------------------------------------
# 2. _client_phase_index -- k/N consistency (the "single most likely way to
#    fail this unit" per the work order: a filtered N with an unfiltered k).
# ---------------------------------------------------------------------------
class TestClientPhaseIndexConsistency:
    def test_counted_phase_gets_a_real_k_within_n(self, tmp_path):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        k, n = rsd._client_phase_index(rd, "P-0.5-RESEARCH", phases)
        assert n == 44
        assert k is not None and 1 <= k <= n

    def test_deferred_phase_gets_k_none_but_real_n(self, tmp_path):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        k, n = rsd._client_phase_index(rd, "P-CONVERTER", phases)
        assert k is None
        assert n == 44  # N is still the honest client-facing total, never None

    def test_every_visible_phase_has_a_unique_k_covering_1_to_n_exactly(self, tmp_path):
        """The hard consistency proof: k for every client-visible phase, taken
        together, is exactly {1..N} with no gaps and no duplicates -- for all
        three named deck types."""
        phases = _manifest_phases()
        for deck_type, creation_mode, expected_n in (
            ("webinar", "from_scratch", 44),
            ("signature_presentation", "from_scratch", 48),
            ("webinar", "content_personal", 45),
        ):
            rd = tmp_path / f"consist-{deck_type}-{creation_mode}"
            rd.mkdir()
            (rd / "working" / "copy").mkdir(parents=True)
            (rd / "working" / "copy" / "intake.json").write_text(
                json.dumps({"deck_type": deck_type, "creation_mode": creation_mode}))
            visible = rsd._client_visible_phases(rd, phases)
            assert len(visible) == expected_n
            ks = []
            for ph in phases:
                k, n = rsd._client_phase_index(rd, ph["id"], phases)
                assert n == expected_n
                if k is not None:
                    ks.append(k)
            assert sorted(ks) == list(range(1, expected_n + 1)), (
                f"k values for deck_type={deck_type!r} creation_mode={creation_mode!r} "
                f"are not exactly 1..{expected_n}: {sorted(ks)}")

    def test_unknown_phase_id_returns_k_none_n_real(self, tmp_path):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        k, n = rsd._client_phase_index(rd, "P-DOES-NOT-EXIST", phases)
        assert k is None
        assert n == 44


# ---------------------------------------------------------------------------
# 3. emit_client_report -- wording for counted vs. deferred phases.
# ---------------------------------------------------------------------------
class TestEmitClientReportWording:
    def test_counted_phase_says_step_k_of_n(self, tmp_path, monkeypatch):
        rd = tmp_path / "run"
        sent = []
        monkeypatch.setattr(rsd, "_send_owner_message",
                            lambda text: (sent.append(text), ("mid", True))[1])
        rsd.emit_client_report(rd, "P-0.5-RESEARCH", "start", k=1, N=31)
        assert sent == ["Step 1 of 31 — P-0.5-RESEARCH — starting"]

    def test_deferred_phase_gets_annotation_not_a_wrong_number(self, tmp_path, monkeypatch):
        rd = tmp_path / "run"
        sent = []
        monkeypatch.setattr(rsd, "_send_owner_message",
                            lambda text: (sent.append(text), ("mid", True))[1])
        rsd.emit_client_report(rd, "P-CONVERTER", "start", k=None, N=31)
        assert len(sent) == 1
        text = sent[0]
        assert "Step" not in text or "31-step plan" in text  # never "Step <n> of 31" for k=None
        assert "P-CONVERTER" in text
        assert "31" in text  # still names the honest total for context
        assert "starting" in text

    def test_totally_unknown_k_and_n_keeps_legacy_wording(self, tmp_path, monkeypatch):
        """Back-compat: a caller that passes neither k nor N (the pre-B2
        contract, still used by callers with no deck context) is untouched."""
        rd = tmp_path / "run"
        sent = []
        monkeypatch.setattr(rsd, "_send_owner_message",
                            lambda text: (sent.append(text), ("mid", True))[1])
        rsd.emit_client_report(rd, "P4-COPY", "done")
        assert sent == ["P4-COPY — complete"]


# ---------------------------------------------------------------------------
# 4. declare_plan -- outbound message honesty + declared_plan.json contract.
# ---------------------------------------------------------------------------
class TestDeclarePlan:
    def _declare(self, tmp_path, monkeypatch, deck_type, creation_mode):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type=deck_type, creation_mode=creation_mode)
        sent = []
        monkeypatch.setattr(rsd, "_send_owner_message",
                            lambda text: (sent.append(text), ("mid-1", True))[1])
        rsd.declare_plan(rd, phases)
        plan = json.loads((rd / "working" / "checkpoints" / "declared_plan.json").read_text())
        return plan, sent

    def test_enforcement_fields_stay_full_36(self, tmp_path, monkeypatch):
        plan, _sent = self._declare(tmp_path, monkeypatch, "webinar", "from_scratch")
        assert plan["total"] == 49  # 55 - 6 VSL-gated defers (fixture intake lacks upsell answers)
        assert len(plan["steps"]) == 49
        ids = {s["id"] for s in plan["steps"]}
        assert "P-CONVERTER" in ids
        for pid in _SP_ONLY:
            assert pid in ids

    def test_client_facing_fields_match_deck_type(self, tmp_path, monkeypatch):
        plan, sent = self._declare(tmp_path, monkeypatch, "webinar", "from_scratch")
        assert plan["client_facing_total"] == 44
        assert len(plan["client_facing_step_ids"]) == 44
        assert "P-CONVERTER" not in plan["client_facing_step_ids"]
        assert "I'll follow these 44 steps" in sent[0]

    def test_signature_deck_message_says_35(self, tmp_path, monkeypatch):
        plan, sent = self._declare(tmp_path, monkeypatch, "signature_presentation", "from_scratch")
        assert plan["client_facing_total"] == 48
        assert "I'll follow these 48 steps" in sent[0]

    def test_content_conversion_deck_message_says_32(self, tmp_path, monkeypatch):
        plan, sent = self._declare(tmp_path, monkeypatch, "webinar", "content_personal")
        assert plan["client_facing_total"] == 45
        assert "I'll follow these 45 steps" in sent[0]

    def test_unknown_deck_shape_message_says_36_not_a_wrong_smaller_number(self, tmp_path, monkeypatch):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, no_intake=True)
        sent = []
        monkeypatch.setattr(rsd, "_send_owner_message",
                            lambda text: (sent.append(text), ("mid-1", True))[1])
        rsd.declare_plan(rd, phases)
        plan = json.loads((rd / "working" / "checkpoints" / "declared_plan.json").read_text())
        assert plan["client_facing_total"] == 55
        assert plan["total"] == 49  # 55 - 6 VSL-gated defers (fixture intake lacks upsell answers)
        assert "I'll follow these 55 steps" in sent[0]

    def test_idempotent_second_call_does_not_resend(self, tmp_path, monkeypatch):
        phases = _manifest_phases()
        rd = _run_dir(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        sent = []
        monkeypatch.setattr(rsd, "_send_owner_message",
                            lambda text: (sent.append(text), ("mid-1", True))[1])
        rsd.declare_plan(rd, phases)
        rsd.declare_plan(rd, phases)
        assert len(sent) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
