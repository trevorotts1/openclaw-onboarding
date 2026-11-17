"""PD-063 — the bundle check reads the run's own files and writes its verdict.

THE DEFECT (Critical finding PD-063). ``bundle_gate.py`` resolved the bundle
folder to ``~/Downloads/<deck-slug>`` — the client's home folder — created it
when absent, templated the deck filenames from the INTERVIEW name rather than
the assembled ``*-FINAL`` name, and wrote no verdict record. Meanwhile
``phase_verifiers._verify_bundle_gate`` REQUIRES
``working/checkpoints/bundle_gate.json``, so the phase could pass and still be
unverifiable.

WHAT THESE TESTS PIN (the PD-063 probe as a test):
  * A1 — a full set of deliverables at the manifest's declared run-dir paths:
    exit 0, verdict ``ok: true``, and NOTHING created under the home folder
    (home is pointed at an empty scratch dir and listed before and after).
  * A2 — speech removed: exit 5 and the verdict file NAMES it.
  * A3 — the deck is found by the ``*-FINAL`` pattern, not by the interview
    name: intake says ``interview-name``, the file is
    ``real-deck-FINAL.pptx``.
  * A4 (control) — ``infographic_png`` is skipped ONLY when the engine's own
    state records ``P8.3-INFOGRAPHIC`` as ``routed_around``; without that state
    the same run exits 5 naming the infographic.

No model, no network, no real deck: stub files are written at the paths the
manifest declares, and every count is read back from the artefacts on disk.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import bundle_gate  # noqa: E402

def _repo_root() -> Path:
    for p in [SCRIPTS] + list(SCRIPTS.parents):
        if (p / "universal-sops").is_dir():
            return p
    raise AssertionError("repo root not found from %s" % SCRIPTS)


def _manifest_file() -> Path:
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    return _repo_root() / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"


MANIFEST = _manifest_file()

VERDICT_REL = Path("working") / "checkpoints" / "bundle_gate.json"

# key -> (run-dir-relative path, leading bytes, minimum size). Sizes clear the
# DELIVERABLES_REQUIRED floors for a stub run with no slides.json (the static
# reference-deck calibration). webinar_mp4 is produced_later: presence only.
STUBS = {
    "deck_pptx":         ("working/deliverables/real-deck-FINAL.pptx", b"PK\x03\x04", 1_048_576),
    "deck_pdf":          ("working/deliverables/real-deck-FINAL.pdf", b"%PDF-1.4\n", 56_000),
    "guide_pdf":         ("working/deliverables/PRESENTER-GUIDE.pdf", b"%PDF-1.4\n", 56_000),
    "speech_md":         ("working/deliverables/PRESENTERS-SPEECH.md", b"# speech\n", 2_100),
    "speech_pdf":        ("working/deliverables/PRESENTERS-SPEECH.pdf", b"%PDF-1.4\n", 3_100),
    "speech_fish_md":    ("working/deliverables/PRESENTERS-SPEECH-FISH-TAGGED.md", b"# fish\n", 2_100),
    "audio_mp3":         ("working/delivery/PRESENTER-AUDIO.mp3", b"ID3", 512_100),
    "infographic_png":   ("working/deliverables/infographic.png", b"\x89PNG", 102_500),
    "teleprompter_html": ("working/deliverables/presenter-teleprompter.html", b"<!DOCTYPE html>\n", 20_100),
    "webinar_mp4":       ("working/delivery/interview-name-WEBINAR.mp4", b"\x00\x00\x00\x18ftyp", 40),
}


def _write(path: Path, lead: bytes, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pad = max(0, size - len(lead))
    path.write_bytes(lead + b"\x00" * pad)


def _manifest_paths() -> list:
    """The exact `consumes` list P-BUNDLE-GATE declares — the acceptance
    surface. Read from the shipped manifest, never hand-copied."""
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for phase in man["phases"]:
        if phase.get("id") == "P-BUNDLE-GATE":
            return list(phase.get("consumes") or [])
    raise AssertionError("P-BUNDLE-GATE is not in %s" % MANIFEST)


def _run(tmp_path: Path, *, omit=(), routed_around: bool = False,
         intake_slug: str = "interview-name") -> Path:
    run = tmp_path / "run"
    (run / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (run / "working" / "copy" / "intake.json").write_text(
        json.dumps({"deck_slug": intake_slug}), encoding="utf-8")
    for key, (rel, lead, size) in STUBS.items():
        if key in omit:
            continue
        _write(run / rel, lead, size)
    if routed_around:
        (run / "state.json").write_text(json.dumps({
            "schema_version": 1, "job_id": "pd063",
            "phases": [{"id": "P8.3-INFOGRAPHIC", "status": "done",
                        "routed_around": True,
                        "routed_around_reason": "no infographic required"}],
        }), encoding="utf-8")
    return run


def _verdict(run: Path) -> dict:
    p = run / VERDICT_REL
    assert p.is_file(), f"the gate wrote no verdict at {VERDICT_REL}"
    return json.loads(p.read_text(encoding="utf-8"))


def test_manifest_declares_ten_deliverables_and_the_verdict_path():
    """The gate's contract surface is the manifest, and the manifest already
    declares working/checkpoints/bundle_gate.json as the phase's artifact."""
    paths = _manifest_paths()
    assert len(paths) == 10, paths
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    phase = next(p for p in man["phases"] if p.get("id") == "P-BUNDLE-GATE")
    assert phase["produces_artifact"] == "working/checkpoints/bundle_gate.json"
    # Every manifest path is one the stubs actually place (or a documented alias).
    def canon(p: str) -> str:
        return p.replace("real-deck", "{deck_slug}").replace(
            "interview-name", "{deck_slug}")

    stub_paths = {canon(v[0]) for v in STUBS.values()}
    stub_names = {canon(Path(v[0]).name) for v in STUBS.values()}
    for rel in paths:
        assert canon(rel) in stub_paths or canon(Path(rel).name) in stub_names, rel


def test_A1_full_set_at_manifest_paths_exits_zero_and_touches_no_home(
        tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    run = _run(tmp_path)
    before = sorted(p.name for p in home.iterdir())

    rc = bundle_gate.main(["--run-dir", str(run)])

    assert rc == 0
    verdict = _verdict(run)
    assert verdict["ok"] is True, verdict
    assert verdict["missing"] == []
    assert verdict["checked_at"].endswith("+00:00")
    # A1's second half: nothing created under the home folder.
    after = sorted(p.name for p in home.iterdir())
    assert after == before == [], after


def test_A2_speech_removed_exits_five_and_the_verdict_names_it(tmp_path: Path):
    run = _run(tmp_path, omit=("speech_md",))
    rc = bundle_gate.main(["--run-dir", str(run)])
    assert rc == 5
    verdict = _verdict(run)
    assert verdict["ok"] is False
    assert any("PRESENTERS-SPEECH.md" in m for m in verdict["missing"]), verdict


def test_A3_deck_found_by_final_pattern_not_the_interview_name(tmp_path: Path):
    """intake says `interview-name`; the assembled deck is `real-deck-FINAL`."""
    run = _run(tmp_path, intake_slug="interview-name")
    assert (run / "working/deliverables/real-deck-FINAL.pptx").is_file()
    assert not (run / "working/deliverables/interview-name-FINAL.pptx").exists()
    assert bundle_gate.main(["--run-dir", str(run)]) == 0


def test_A4_infographic_skipped_only_when_state_says_routed_around(tmp_path: Path):
    """CONTROL: the same run passes with the routed_around state and fails
    without it — the exemption is the engine's record, nothing else."""
    passed = _run(tmp_path / "with-state", omit=("infographic_png",),
                  routed_around=True)
    assert bundle_gate.main(["--run-dir", str(passed)]) == 0
    assert _verdict(passed)["missing"] == []

    failed = _run(tmp_path / "no-state", omit=("infographic_png",))
    assert bundle_gate.main(["--run-dir", str(failed)]) == 5
    verdict = _verdict(failed)
    assert any("infographic.png" in m for m in verdict["missing"]), verdict


def test_rejected_files_are_named_not_silently_passed(tmp_path: Path):
    """A symlink is present-but-rejected (the postflight C2 rule the run-folder
    gate keeps), and an under-floor file is named."""
    run = _run(tmp_path, omit=("guide_pdf", "speech_pdf"))
    _write(run / "working/deliverables/PRESENTERS-SPEECH.pdf", b"%PDF-1.4\n", 100)
    (run / "working/deliverables/PRESENTER-GUIDE.pdf").symlink_to(
        run / "working/deliverables/PRESENTER-GUIDE-target.pdf")
    _write(run / "working/deliverables/PRESENTER-GUIDE-target.pdf",
           b"%PDF-1.4\n", 56_000)
    rc = bundle_gate.main(["--run-dir", str(run)])
    assert rc == 5
    missing = _verdict(run)["missing"]
    assert "working/deliverables/PRESENTER-GUIDE.pdf" in missing
    assert "working/deliverables/PRESENTERS-SPEECH.pdf" in missing


def test_no_home_downloads_fallback_survives_in_the_source():
    """A behavioural guard cannot see a dead fallback: assert the string is
    gone from the gate's own source."""
    src = Path(bundle_gate.__file__).read_text(encoding="utf-8")
    assert "Path.home()" not in src
    assert '"Downloads"' not in src
