"""Tests for B2b (MASTER-WORK-ORDER-20260818 Wave B, unit B2b) -- the
CLIENT-FACING client_report rendering in presentation_job/phases.py (the
ENGINE path presentation-canonical-entry.sh actually dispatches in
production, in preference to the legacy run_signature_deck.py runner B2
fixed -- see the entry script's ENGINE_ENTRY dispatch block).

Ground truth this file pins (FABLE-TRUTH.md SS1 / MASTER-WORK-ORDER B2, same
as test_client_step_count.py's ground truth for the runner side):
  * 36 is the enforced, machine-walked phase count in PIPELINE-MANIFEST.json --
    UNCHANGED here. This file never touches self.manifest.phases, the DAG,
    declared_plan.json, or the attestation chain -- only proves the
    CLIENT-FACING helper methods (_client_deck_shape / _client_visible_phases /
    _client_phase_index / _render_client_report_msg) added to Engine.
  * 31 phases are client-visible on a standard from-scratch deck (5
    conditional pass-throughs: P-CONVERTER + the four P-SP-* signature-only
    phases). 35 on a signature deck. 32 on a content-conversion deck.
    P-SP-CLAIM is the routing gate and runs for real on EVERY deck -- never
    filtered.
  * THE DEFECT THIS FILE PROVES FIXED: before B2b, Engine.run_phase() read
    phase.client_report["start_template"]/["done_template"] straight off the
    manifest -- literally "Step {k} of {N} -- {name} -- starting{eta}" -- and
    handed that STRING, UNFORMATTED, to the client. No .format()/format_map()
    call existed anywhere in phases.py. This is worse than the "Step 5 of 36"
    over-count problem B2 fixed in the runner (which is not even the
    production dispatch path -- see presentation-canonical-entry.sh): it is
    unreadable, not just numerically dishonest.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_client_step_count.py, test_report.py, etc.).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest, Phase  # noqa: E402
from presentation_job.phases import Engine, _SafeFormatDict  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _canonical_manifest() -> Path:
    """Locate the canonical PIPELINE-MANIFEST.json the way the deployed tree
    and the repo tree carry it -- identical resolution order to
    test_presentation_job.py's _canonical_manifest() and
    test_client_step_count.py's _manifest_phases()."""
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError(
        "PIPELINE-MANIFEST.json not found (looked in scripts/../sops/ and the "
        "universal-sops/presentation-slide-craft walk-up)")


def _manifest() -> Manifest:
    return Manifest(_canonical_manifest())


_SP_ONLY = ("P-SP-INTAKE", "P-SP-INTAKE-TRACE", "P-SP-STRUCTURE", "P-SP-P3-HYGIENE")


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


def _engine(tmp_path, deck_type=None, creation_mode=None, no_intake=False) -> Engine:
    """A real Engine wired to the canonical manifest, a scratch run_dir, and a
    minimal but schema-complete state dict (same shape test_report.py's
    _mkstate uses). BoardMirror construction is expected to fail (no CC env
    configured in a test) -- Engine.__init__ already catches that and sets
    self.board = None, so no monkeypatching is needed here."""
    rd = _run_dir(tmp_path, deck_type=deck_type, creation_mode=creation_mode, no_intake=no_intake)
    manifest = _manifest()
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": manifest.version, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=True)


# ---------------------------------------------------------------------------
# 0. The enforced 36 -- proof it is untouched by this unit.
# ---------------------------------------------------------------------------
class TestEnforcedCountUnchanged:
    def test_manifest_has_36_phases(self):
        assert len(_manifest().phases) == 55  # 36 + Wave C unit C1's 4 upsell phases (manifest_version 51)

    def test_client_visible_phases_never_mutates_input(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        before = [p.id for p in eng.manifest.phases]
        eng._client_visible_phases(eng.manifest.phases)
        after = [p.id for p in eng.manifest.phases]
        assert before == after, "the raw manifest phase list must never be filtered in place"

    def test_verifier_registry_covers_all_36(self):
        """Independent proof (not just phases[]) that the 36-phase enforcement
        surface phase_verifiers.py registers is untouched by this unit."""
        import phase_verifiers
        ids = {p.id for p in _manifest().phases}
        registered = set(phase_verifiers.PHASE_VERIFIERS.keys())
        missing = ids - registered
        assert not missing, f"phase_verifiers.py is missing verifiers for: {sorted(missing)}"


# ---------------------------------------------------------------------------
# 1. _client_visible_phases -- the three named deck types + fail-safe unknown.
# ---------------------------------------------------------------------------
class TestClientVisibleCounts:
    def test_standard_from_scratch_is_31(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        visible = eng._client_visible_phases(eng.manifest.phases)
        assert len(visible) == 44  # 31 + 4 upsell phases (flags unset -> unknown widens)
        ids = {p.id for p in visible}
        assert "P-CONVERTER" not in ids
        for pid in _SP_ONLY:
            assert pid not in ids

    def test_signature_is_35(self, tmp_path):
        eng = _engine(tmp_path, deck_type="signature_presentation", creation_mode="from_scratch")
        visible = eng._client_visible_phases(eng.manifest.phases)
        assert len(visible) == 48  # 35 + 4 upsell phases (flags unset -> unknown widens)
        ids = {p.id for p in visible}
        assert "P-CONVERTER" not in ids
        for pid in _SP_ONLY:
            assert pid in ids

    def test_content_conversion_is_32(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="content_personal")
        visible = eng._client_visible_phases(eng.manifest.phases)
        assert len(visible) == 45  # 32 + 4 upsell phases (flags unset -> unknown widens)
        ids = {p.id for p in visible}
        assert "P-CONVERTER" in ids
        for pid in _SP_ONLY:
            assert pid not in ids

    def test_content_conversion_general_mode_also_32(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="content_general")
        assert len(eng._client_visible_phases(eng.manifest.phases)) == 45  # 32 + 13 P-U (merged 2026-09-01)

    def test_unknown_intake_fails_safe_to_full_36(self, tmp_path):
        eng = _engine(tmp_path, no_intake=True)
        assert len(eng._client_visible_phases(eng.manifest.phases)) == 55

    def test_empty_intake_object_fails_safe_to_full_36(self, tmp_path):
        eng = _engine(tmp_path)  # writes {} -- both fields absent
        assert len(eng._client_visible_phases(eng.manifest.phases)) == 55

    def test_unreadable_intake_json_fails_safe(self, tmp_path):
        eng = _engine(tmp_path)
        (eng.run_dir / "working" / "copy" / "intake.json").write_text("{not valid json")
        assert len(eng._client_visible_phases(eng.manifest.phases)) == 55

    def test_deck_type_known_but_creation_mode_unknown_only_filters_sp(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode=None)
        ids = {p.id for p in eng._client_visible_phases(eng.manifest.phases)}
        assert "P-CONVERTER" in ids  # creation_mode unknown -> not filtered
        for pid in _SP_ONLY:
            assert pid not in ids  # deck_type positively known non-signature -> filtered

    def test_sp_claim_never_filtered_on_any_deck_type(self, tmp_path):
        for dt, cm in (("webinar", "from_scratch"),
                       ("signature_presentation", "from_scratch"),
                       ("webinar", "content_personal"),
                       (None, None)):
            eng = _engine(tmp_path / f"r-{dt}-{cm}", deck_type=dt, creation_mode=cm)
            ids = {p.id for p in eng._client_visible_phases(eng.manifest.phases)}
            assert "P-SP-CLAIM" in ids, f"P-SP-CLAIM filtered for deck_type={dt!r} creation_mode={cm!r}"


# ---------------------------------------------------------------------------
# 2. _client_phase_index -- k/N consistency (the "single most likely way to
#    fail this unit" per the work order: a filtered N with an unfiltered k).
# ---------------------------------------------------------------------------
class TestClientPhaseIndexConsistency:
    def test_counted_phase_gets_a_real_k_within_n(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        k, n = eng._client_phase_index("P-0.5-RESEARCH", eng.manifest.phases)
        assert n == 44
        assert k is not None and 1 <= k <= n

    def test_deferred_phase_gets_k_none_but_real_n(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        k, n = eng._client_phase_index("P-CONVERTER", eng.manifest.phases)
        assert k is None
        assert n == 44

    def test_every_visible_phase_has_a_unique_k_covering_1_to_n_exactly(self, tmp_path):
        """The hard consistency proof, mirroring test_client_step_count.py's
        twin: k for every client-visible phase, taken together, is exactly
        {1..N} with no gaps and no duplicates -- for all three named deck
        types. This is the check that catches 'a filtered N with an
        unfiltered k' -- the failure mode the work order names as most
        likely."""
        for deck_type, creation_mode, expected_n in (
            ("webinar", "from_scratch", 44),
            ("signature_presentation", "from_scratch", 48),
            ("webinar", "content_personal", 45),
        ):
            eng = _engine(tmp_path / f"consist-{deck_type}-{creation_mode}",
                          deck_type=deck_type, creation_mode=creation_mode)
            visible = eng._client_visible_phases(eng.manifest.phases)
            assert len(visible) == expected_n
            ks = []
            for ph in eng.manifest.phases:
                k, n = eng._client_phase_index(ph.id, eng.manifest.phases)
                assert n == expected_n
                if k is not None:
                    ks.append(k)
            assert sorted(ks) == list(range(1, expected_n + 1)), (
                f"k values for deck_type={deck_type!r} creation_mode={creation_mode!r} "
                f"are not exactly 1..{expected_n}: {sorted(ks)}")

    def test_unknown_phase_id_returns_k_none_n_real(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        k, n = eng._client_phase_index("P-DOES-NOT-EXIST", eng.manifest.phases)
        assert k is None
        assert n == 44


# ---------------------------------------------------------------------------
# 3. _render_client_report_msg -- THE core B2b proof: {k}/{N}/{name}/{eta}
#    are ACTUALLY substituted, never left as literal braces.
# ---------------------------------------------------------------------------
class TestRenderClientReportMsgNoLiteralBraces:
    def test_no_literal_brace_reaches_output_for_any_phase_any_deck_shape(self, tmp_path):
        """THE headline proof for VERIFY #5: sweep every one of the 36
        phases, both 'start' and 'done', across all three named deck shapes
        AND the unknown-shape case -- not one rendered message may contain a
        '{' or '}' character. Before B2b this failed on all 36 phases x 2
        kinds x every deck shape, because the manifest's raw
        'Step {k} of {N} -- {name} -- starting{eta}' string was sent
        verbatim."""
        cases = [
            ("webinar", "from_scratch"),
            ("signature_presentation", "from_scratch"),
            ("webinar", "content_personal"),
            (None, None),  # unknown deck shape -- fail-safe path
        ]
        for deck_type, creation_mode in cases:
            eng = _engine(tmp_path / f"braces-{deck_type}-{creation_mode}",
                          deck_type=deck_type, creation_mode=creation_mode)
            for ph in eng.manifest.phases:
                for kind in ("start", "done"):
                    msg = eng._render_client_report_msg(ph, kind)
                    assert "{" not in msg and "}" not in msg, (
                        f"literal brace leaked to client: phase={ph.id} kind={kind} "
                        f"deck_type={deck_type!r} creation_mode={creation_mode!r} msg={msg!r}")

    def test_counted_phase_substitutes_real_k_n_name(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        ph = eng.manifest.phase("P-0.5-RESEARCH")
        assert ph.name == "Deep Research"
        msg = eng._render_client_report_msg(ph, "start")
        assert msg == "Step 1 of 44 — Deep Research — starting", msg
        done = eng._render_client_report_msg(ph, "done")
        assert done == "Step 1 of 44 — Deep Research — complete", done

    def test_name_field_used_not_bare_phase_id(self, tmp_path):
        """{name} resolves to the manifest's declared 'name' (a human string),
        not the machine phase id -- proves Phase.name (manifest.py) is wired,
        not just defaulting to phase.id every time."""
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        ph = eng.manifest.phase("P4-RENDER")
        assert ph.name and ph.name != ph.id
        msg = eng._render_client_report_msg(ph, "start")
        assert ph.name in msg
        assert "{name}" not in msg

    def test_eta_placeholder_empty_when_no_eta_declared(self, tmp_path):
        """None of the 36 manifest phases declare eta_minutes today -- {eta}
        must resolve to '' (dropping the token cleanly), never leak
        '{eta}' or crash."""
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        ph = eng.manifest.phase("P0A-INTAKE")
        msg = eng._render_client_report_msg(ph, "start")
        assert "{eta}" not in msg
        assert msg.endswith("starting"), msg  # no trailing junk where {eta} was

    def test_eta_substituted_when_present(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        ph = eng.manifest.phase("P0A-INTAKE")
        ph.client_report = dict(ph.client_report)
        ph.client_report["eta_minutes"] = 12
        msg = eng._render_client_report_msg(ph, "start")
        assert "ETA ~12 min" in msg
        assert "{eta}" not in msg
        done = eng._render_client_report_msg(ph, "done")
        assert "ETA" not in done  # ETA only ever appended to the start message

    def test_deferred_phase_gets_honest_wording_not_a_wrong_step_number(self, tmp_path):
        """P-CONVERTER on a standard from-scratch deck: walked/attested (the
        36-phase enforcement never skips it) but NOT one of this deck's 31
        client-visible steps. Must not fabricate 'Step <n> of 31'."""
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        ph = eng.manifest.phase("P-CONVERTER")
        msg = eng._render_client_report_msg(ph, "start")
        assert "Step" not in msg or "35-step plan" in msg
        assert "P-CONVERTER" in msg
        assert "44" in msg  # still names the honest total for context
        assert "{" not in msg and "}" not in msg

    def test_sp_only_phase_deferred_on_standard_deck(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        ph = eng.manifest.phase("P-SP-INTAKE")
        msg = eng._render_client_report_msg(ph, "start")
        assert "44-step plan" in msg
        assert "{" not in msg and "}" not in msg

    def test_malformed_template_falls_back_to_default_not_a_crash_or_leak(self, tmp_path):
        """A manifest client_report template with a stray unmatched brace must
        never propagate to the client verbatim, and must never raise."""
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        ph = eng.manifest.phase("P4-COPY")
        ph.client_report = {"start_template": "Step {k of {N} -- broken"}
        msg = eng._render_client_report_msg(ph, "start")
        assert msg == f"Starting {ph.id} ({ph.owning_role})"
        assert "{" not in msg and "}" not in msg

    def test_no_template_declared_uses_plain_default(self, tmp_path):
        eng = _engine(tmp_path, deck_type="webinar", creation_mode="from_scratch")
        ph = eng.manifest.phase("P4-COPY")
        ph.client_report = {}
        assert eng._render_client_report_msg(ph, "start") == f"Starting {ph.id} ({ph.owning_role})"
        assert eng._render_client_report_msg(ph, "done") == f"{ph.id} complete"

    def test_unrecognized_token_in_template_drops_cleanly(self):
        """_SafeFormatDict: a template referencing a token this engine does
        not populate degrades that ONE token to '' rather than KeyError."""
        fields = _SafeFormatDict(k=1, N=31, name="X", eta="")
        assert "{unknown_token}".format_map(fields) == ""
        assert "Step {k} of {N}".format_map(fields) == "Step 1 of 31"


# ---------------------------------------------------------------------------
# 4. Real production templates (proves the ACTUAL manifest.client_report
#    dicts -- not a synthetic stand-in -- format cleanly for every phase).
# ---------------------------------------------------------------------------
class TestRealManifestTemplates:
    def test_every_phase_declares_the_step_k_of_n_template(self):
        """Pins the ground truth this unit was dispatched to fix: every one
        of the 36 phases in the real manifest declares a start_template
        containing '{k}' and '{N}' -- so the bug (unformatted output) would
        have fired on literally every phase, every run, on the engine path."""
        m = _manifest()
        for ph in m.phases:
            st = ph.client_report.get("start_template", "")
            assert "{k}" in st and "{N}" in st, f"{ph.id} lost its Step k of N template"

    def test_all_36_phases_render_without_a_brace_leaking_signature_deck(self, tmp_path):
        eng = _engine(tmp_path, deck_type="signature_presentation", creation_mode="from_scratch")
        for ph in eng.manifest.phases:
            for kind in ("start", "done"):
                msg = eng._render_client_report_msg(ph, kind)
                assert "{" not in msg and "}" not in msg


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
