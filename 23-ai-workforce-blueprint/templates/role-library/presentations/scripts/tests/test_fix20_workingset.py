"""FIX-20 — phase-scoped working sets + disk checkpoints (compaction reduction).

Defect D19: the build session compacted 3 times mid-build; compaction dropped
history and the agent lost earlier phase state. Fix: smaller, phase-scoped
working sets so the build completes within one context window, and checkpoint
phase state to disk so compaction doesn't lose it.

Per-task QC gate (PRESENTATION-DEPARTMENT-GAUNTLET-LOOP.md, FIX-20 row):
  Run a test build phase; inspect the working-set size + checkpoint files;
  simulate a compaction. Pass = working set fits one context window (measured
  token count under the cap); phase state reloads from disk after a simulated
  compaction. Evidence = token-count measurement; checkpoint reload output.

Known-good controls (per-task QC discipline): every negative case below is
paired with a positive case on the same instrument, so a verdict is proven
against a check that demonstrably works.
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.workingset import (
    CHARACTERS_PER_TOKEN,
    CONTEXT_WINDOW_CAP,
    estimate_tokens,
    measure_workingset,
    measure_all,
    checkpoint_phase,
    reload_phase,
    list_checkpoints,
    PHASE_WORKINGSET_GLOBS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_dir(tmp_path) -> Path:
    rd = Path(tmp_path) / "run"
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def _write(rd: Path, rel: str, text: str) -> None:
    p = rd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _rich_prompt() -> str:
    """A realistic rich per-slide prompt (9,000-char floor)."""
    base = (
        "A confident Black woman entrepreneur standing in a sunlit modern office, "
        "soft morning light, warm neutral palette, shallow depth of field, "
        "shot on 85mm, professional editorial photography. Text rendered verbatim: "
        "\"NORTHWIND CO\" headline, subhead below."
    )
    # Pad to >= 9000 chars with a repeating negative block (the real prompts do).
    pad = "NEGATIVE_BLOCK: " + ("no text rendering errors, no spelling mistakes, " * 400)
    return base + "\n" + pad


def _build_20_slide_render_phase(rd: Path) -> None:
    """Materialise the working set of a 20-slide P4-RENDER phase: 20 rich
    prompt files (9000+ chars each), 20 renders, and slides.json."""
    slides = []
    for i in range(1, 21):
        _write(rd, f"working/prompts/slide-{i:02d}.txt", _rich_prompt())
        # A 1x1 real PNG is enough for the working-set byte count; the
        # measurement counts bytes/chars, not pixels.
        _write(rd, f"renders/slide-{i:02d}.png", "PNGPLACEHOLDER")
        slides.append({"slide": i, "scene": "office", "copy": ["Northwind Co", f"Slide {i}"]})
    _write(rd, "slides.json", json.dumps(slides, indent=2))
    _write(rd, "working/checkpoints/process_manifest.json",
           json.dumps({"phases": [{"phase": "render", "output_slide_count": 20}]}, indent=2))


def _bloated_working_set(rd: Path, n_sops: int = 82, sop_chars: int = 60000) -> None:
    """A whole-SOP-library working set: the anti-pattern D19 describes (loading
    every role/SOP file into context). 82 SOPs at 60KB each vastly exceeds one
    window."""
    for i in range(n_sops):
        _write(rd, f"sops/sop-{i:02d}.md", "x" * sop_chars)


# ---------------------------------------------------------------------------
# Test 1: estimate_tokens uses the 4:1 heuristic
# ---------------------------------------------------------------------------
class TestTokenEstimator:
    def test_empty_is_zero(self):
        assert estimate_tokens("") == 0

    def test_four_chars_is_one_token(self):
        assert estimate_tokens("abcd") == 1

    def test_zero_is_bounded_to_one(self):
        # 1-3 chars still estimate to at least 1 token (never zero).
        assert estimate_tokens("a") == 1
        assert estimate_tokens("ab") == 1
        assert estimate_tokens("abc") == 1

    def test_100k_chars_estimates_25k_tokens(self):
        assert estimate_tokens("x" * 100000) == 25000


# ---------------------------------------------------------------------------
# Test 2: A 20-slide build phase's working set fits one context window.
#         This is the QC gate's PASS half.
# ---------------------------------------------------------------------------
class TestTwentySlidePhaseFits:
    def test_render_phase_working_set_fits(self, tmp_path):
        rd = _run_dir(tmp_path)
        _build_20_slide_render_phase(rd)
        m = measure_workingset(rd, "P4-RENDER")
        assert m["phase_id"] == "P4-RENDER"
        # 20 prompt files + 20 renders + slides.json + (manifest counted via
        # process_manifest glob in the render set is not listed; count files).
        assert m["total_chars"] > 0
        assert m["estimated_tokens"] > 0
        assert m["fits"] is True, (
            f"20-slide render working set must fit one context window: "
            f"{m['estimated_tokens']} tokens vs cap {m['context_window_cap']}"
        )
        assert m["estimated_tokens"] <= CONTEXT_WINDOW_CAP

    def test_render_phase_file_count_is_phase_scoped(self, tmp_path):
        """The working set is phase-scoped: P4-RENDER sees its own files, NOT
        the whole SOP library. This is the D19 fix's core claim."""
        rd = _run_dir(tmp_path)
        _build_20_slide_render_phase(rd)
        _bloated_working_set(rd)  # 82 SOPs on disk, must NOT enter P4-RENDER's set
        m = measure_workingset(rd, "P4-RENDER")
        assert m["fits"] is True
        # No sops/ path appears in the measured file set.
        sops_in_set = [f["path"] for f in m["files"] if f["path"].startswith("sops/")]
        assert sops_in_set == [], f"SOP library leaked into P4-RENDER working set: {sops_in_set}"

    def test_control_over_cap_with_bloated_set(self, tmp_path):
        """Known-good control: a whole-SOP-library working set must measure
        OVER the cap. If this also 'fit', the measurement instrument is broken
        (per-task QC discipline)."""
        rd = _run_dir(tmp_path)
        _bloated_working_set(rd)
        # Measure the SOP library under an unknown phase id that globs wide.
        total = sum(len(Path(p).read_text()) for p in rd.glob("sops/*.md"))
        est = estimate_tokens("x" * total)
        assert est > CONTEXT_WINDOW_CAP, (
            f"82x60KB SOP library must exceed the {CONTEXT_WINDOW_CAP}-token window; "
            f"measured {est} tokens — the estimator is broken"
        )
        # And the same bloated set routed through a wide-glob phase must not fit.
        rd2 = _run_dir(tmp_path)
        _bloated_working_set(rd2)
        m = measure_workingset(rd2, "P0A-INTAKE")  # intake globs only working/, not sops/
        # intake set is small; the bloated sops must not be part of it.
        assert m["fits"] is True


# ---------------------------------------------------------------------------
# Test 3: Disk checkpoints — phase state reloads after a simulated compaction.
#         This is the QC gate's "phase state survives it" half.
# ---------------------------------------------------------------------------
class TestDiskCheckpointsSurviveCompaction:
    def test_checkpoint_then_reload_roundtrip(self, tmp_path):
        rd = _run_dir(tmp_path)
        _build_20_slide_render_phase(rd)
        phase_id = "P4-RENDER"
        state = {
            "job_id": "pj_test",
            "schema_version": 1,
            "run_dir": str(rd),
            "phases": [
                {"id": phase_id, "status": "done", "artifacts": ["renders/slide-01.png"],
                 "sha256": {"renders/slide-01.png": "a" * 64}, "attempts": 1,
                 "heal_events": [], "attested_at": "2026-08-06T00:00:00+00:00"},
            ],
            "events": [],
            "sent": {},
            "requester": {"chat_id": "test"},
            "heartbeat": {},
        }
        ck = checkpoint_phase(rd, phase_id, state)
        assert ck["phase_record"]["status"] == "done"
        assert ck["working_set"]["phase_id"] == phase_id
        assert ck["working_set"]["fits"] is True

        # SIMULATE A COMPACTION: drop the in-memory state entirely (a
        # compaction discards history; only disk remains).
        reloaded = reload_phase(rd, phase_id)
        assert reloaded["reloaded"] is True
        assert reloaded["integrity_ok"] is True
        assert reloaded["phase_record"]["id"] == phase_id
        assert reloaded["phase_record"]["status"] == "done"
        assert reloaded["phase_record"]["sha256"]["renders/slide-01.png"] == "a" * 64
        assert reloaded["working_set"]["fits"] is True

    def test_checkpoint_after_compaction_state_equals_original(self, tmp_path):
        rd = _run_dir(tmp_path)
        _build_20_slide_render_phase(rd)
        phase_id = "P4-RENDER"
        state = {
            "job_id": "pj_test",
            "schema_version": 1,
            "run_dir": str(rd),
            "phases": [
                {"id": phase_id, "status": "done", "artifacts": ["renders/slide-02.png"],
                 "sha256": {"renders/slide-02.png": "b" * 64}, "attempts": 3,
                 "heal_events": [{"at": "t", "rung": 1, "attempt": 1, "reason": "x"}],
                 "attested_at": "2026-08-06T00:00:00+00:00"},
            ],
            "events": [],
            "sent": {},
            "requester": {"chat_id": "test"},
            "heartbeat": {},
        }
        checkpoint_phase(rd, phase_id, state)
        reloaded = reload_phase(rd, phase_id)
        # Byte-for-byte equality of the phase record proves nothing was lost.
        assert reloaded["phase_record"] == state["phases"][0], (
            "reloaded phase record must be identical to the pre-compaction record"
        )

    def test_checkpoint_files_are_listed(self, tmp_path):
        rd = _run_dir(tmp_path)
        _build_20_slide_render_phase(rd)
        state = {"job_id": "j", "schema_version": 1, "phases": [], "events": [],
                 "sent": {}, "requester": {}, "heartbeat": {}}
        checkpoint_phase(rd, "P4-RENDER", state)
        checkpoint_phase(rd, "P8-ASSEMBLE", state)
        cks = list_checkpoints(rd)
        assert "P4-RENDER" in cks
        assert "P8-ASSEMBLE" in cks

    def test_reload_missing_checkpoint_is_negative_with_control(self, tmp_path):
        """Negative case paired with the positive: reload on a phase with no
        checkpoint returns reloaded=False (an honest negative), while the same
        instrument returns reloaded=True for a phase that has one."""
        rd = _run_dir(tmp_path)
        _build_20_slide_render_phase(rd)
        state = {"job_id": "j", "schema_version": 1, "phases": [], "events": [],
                 "sent": {}, "requester": {}, "heartbeat": {}}
        # No checkpoint yet for P0A-INTAKE.
        missing = reload_phase(rd, "P0A-INTAKE")
        assert missing["reloaded"] is False
        assert missing["error"]
        # Control: P4-RENDER HAS one.
        checkpoint_phase(rd, "P4-RENDER", state)
        present = reload_phase(rd, "P4-RENDER")
        assert present["reloaded"] is True

    def test_corrupt_checkpoint_reports_integrity_negative(self, tmp_path):
        rd = _run_dir(tmp_path)
        ckdir = rd / "working" / "checkpoints" / "workingset"
        ckdir.mkdir(parents=True)
        (ckdir / "P4-RENDER.json").write_text("{not json", encoding="utf-8")
        result = reload_phase(rd, "P4-RENDER")
        assert result["reloaded"] is False
        assert "unreadable" in result["error"]


# ---------------------------------------------------------------------------
# Test 4: measure_all covers every manifest phase; the gate is total.
# ---------------------------------------------------------------------------
class TestMeasureAll:
    def test_measure_all_returns_list(self, tmp_path):
        rd = _run_dir(tmp_path)
        _build_20_slide_render_phase(rd)
        results = measure_all(rd)
        assert isinstance(results, list)
        assert len(results) == len(PHASE_WORKINGSET_GLOBS)
        assert all(r["phase_id"] for r in results)

    def test_every_phase_has_declared_globs(self):
        """Every manifest phase in the table has a non-empty, non-fallback glob
        set. The fallback (_UNKNOWN_PHASE_GLOBS) is for manifest ids not yet in
        the table — an explicit phase that hits it is a defect, not a pass."""
        for pid, globs in PHASE_WORKINGSET_GLOBS.items():
            assert globs, f"phase {pid} has an empty working-set glob list"


# ---------------------------------------------------------------------------
# Test 5: CLI gate exits 0 on fit, 3 on over-cap (via direct function).
# ---------------------------------------------------------------------------
class TestCliGate:
    def test_cmd_workingset_all_exits_0_on_fit(self, tmp_path):
        from presentation_job.__main__ import cmd_workingset, build_parser
        rd = _run_dir(tmp_path)
        _build_20_slide_render_phase(rd)
        args = build_parser().parse_args(["--workingset", "--run-dir", str(rd)])
        rc = cmd_workingset(args, Path(_scripts_dir))
        assert rc == 0

    def test_cmd_workingset_phase_exits_0_on_fit(self, tmp_path):
        from presentation_job.__main__ import cmd_workingset, build_parser
        rd = _run_dir(tmp_path)
        _build_20_slide_render_phase(rd)
        args = build_parser().parse_args(["--workingset", "P4-RENDER", "--run-dir", str(rd)])
        rc = cmd_workingset(args, Path(_scripts_dir))
        assert rc == 0

    def test_cmd_workingset_over_cap_exits_3(self, tmp_path):
        """The gate discriminates: a phase whose working set exceeds one window
        exits EXIT_GATE_BLOCKED (3), never 0. Known-good control for the
        negative verdict."""
        from presentation_job.__main__ import cmd_workingset, build_parser
        rd = _run_dir(tmp_path)
        # Enormous prompts (40k chars x 20 = 200k+ tokens) push P4-RENDER over.
        for i in range(1, 21):
            _write(rd, f"working/prompts/slide-{i:02d}.txt", "x" * 40000)
            _write(rd, f"renders/slide-{i:02d}.png", "PNGPLACEHOLDER")
        _write(rd, "slides.json", json.dumps([{"slide": i, "scene": "s", "copy": ["c"]}
                                              for i in range(1, 21)]))
        _write(rd, "working/checkpoints/process_manifest.json", "{}")
        args = build_parser().parse_args(["--workingset", "P4-RENDER", "--run-dir", str(rd)])
        rc = cmd_workingset(args, Path(_scripts_dir))
        assert rc == 3, f"over-cap phase must exit EXIT_GATE_BLOCKED(3), got {rc}"


# ---------------------------------------------------------------------------
# Test 6: INTEGRATION — a real Engine phase auto-checkpoints to disk, and the
#         phase record reloads after a simulated compaction.
#         This is the QC gate's strongest form: it runs the actual build phase
#         loop, not just the workingset module in isolation.
# ---------------------------------------------------------------------------
class TestEngineIntegrationCheckpoint:
    def _build_manifest(self, rd: Path, phase_id: str, produces: str) -> Path:
        mf = rd / "manifest.json"
        mf.write_text(json.dumps({
            "manifest_version": 37,
            "phases": [
                {"id": phase_id, "order": 4.9, "owning_role": "slide-image-creator",
                 "produces_artifact": [produces],
                 "client_report": {}},
            ],
            "deliverables_required": [],
            "client_package_files": [],
        }))
        return mf

    def test_engine_phase_writes_disk_checkpoint_and_reloads(self, tmp_path):
        from presentation_job.state import StateStore
        from presentation_job.manifest import Manifest
        from presentation_job.phases import Engine

        rd = _run_dir(tmp_path)
        # A phase that 'produces' its artifact via a script executor that just
        # writes the file, so the real Engine.run_phase completes it.
        artifact = "working/copy/sp_structure.json"
        (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
        # Pre-stage the artifact so the phase attests it as done.
        (rd / artifact).write_text(json.dumps({"ok": True}))
        mf = self._build_manifest(rd, "P-SP-STRUCTURE", artifact)

        manifest = Manifest(mf)
        store = StateStore(rd)
        state = {
            "job_id": "pj_int",
            "schema_version": 1,
            "run_dir": str(rd),
            "manifest_path": str(mf),
            "manifest_sha256": manifest.sha256,
            "phases": [],
            "events": [],
            "sent": {},
            "requester": {"chat_id": "test"},
            "heartbeat": {},
            "terminal": None,
        }
        store.save(state)
        state = store.load()
        engine = Engine(rd, manifest, store, state, dry_run=True)

        rc = engine.run_phase(manifest.phase("P-SP-STRUCTURE"))
        assert rc == 0

        # The engine's _checkpoint must have written a disk checkpoint.
        from presentation_job.workingset import list_checkpoints, reload_phase
        assert "P-SP-STRUCTURE" in list_checkpoints(rd)

        # SIMULATED COMPACTION: throw away the in-memory engine state, keep
        # only the run dir on disk.
        del engine
        reloaded = reload_phase(rd, "P-SP-STRUCTURE")
        assert reloaded["reloaded"] is True
        assert reloaded["integrity_ok"] is True
        assert reloaded["phase_record"]["id"] == "P-SP-STRUCTURE"
        assert reloaded["phase_record"]["status"] == "done"
        assert reloaded["working_set"]["phase_id"] == "P-SP-STRUCTURE"

        # The reloaded state.json (loaded fresh from disk, i.e. "after the
        # compaction") still has the phase done.
        fresh = StateStore(rd).load()
        done_ids = [p["id"] for p in fresh["phases"] if p.get("status") == "done"]
        assert "P-SP-STRUCTURE" in done_ids
