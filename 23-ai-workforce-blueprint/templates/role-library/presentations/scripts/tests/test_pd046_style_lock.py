"""PD-046 — a recorded style pick must pass the render check.

The AF-STYLE-DOUBLECHARGE branch of `_chk_style_preview` refused every pick the
ONE sanctioned recorder writes, because `deck-intake-driver.py --style-pick`
records `owner_approved` + `chosen_variant` and never writes `locked_renders`
(the dispatcher has no writer of that field either). The winner's representative
renders were already on disk in the samples manifest `run_style_preview_samples`
itself writes, so the check now derives them from that manifest's own
`samples[]` rows and holds the derived list to the same "every listed file must
exist" test. An explicit `locked_renders` list is untouched; the unpicked
refusal is untouched.

Acceptance rows (PD-046): A1 the file the real driver writes passes; A2 the
engine auto-pick shape passes; A3 a deleted winner render is still refused;
A4 no pick is still AF-STYLE-UNPICKED; A5 the probe reports NOT CONFIRMED and
the same instrument still reports the trap when a render is gone.

No network, no model call, no live service: the fixtures are files and the
driver runs as a child process against them.
"""
import json
import subprocess
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

import build_deck as bd  # noqa: E402

DRIVER = _scripts_dir / "deck-intake-driver.py"
SAMPLES_REL = "working/style-preview/style_samples_manifest.json"
CHOICE_REL = "working/copy/style_preview_choice.json"
WINNER = "B"
REP_SLIDES = (1, 7, 12)


# ---------------------------------------------------------------------------
# fixtures — the shape P-STYLE-PREVIEW really writes
# ---------------------------------------------------------------------------
def _seed_run(root: Path, variants=("A", "B", "C")) -> Path:
    """A run folder as `run_style_preview_samples` leaves it: the manifest it
    writes (samples[] rows carry variant / slide / render / taskId, render
    relative to the run dir) plus the 3x3 sample PNGs."""
    run = root / "run"
    samples = []
    for variant in variants:
        for ordn in REP_SLIDES:
            rel = f"working/style-preview/variant-{variant}-slide-{ordn:02d}.png"
            png = run / rel
            png.parent.mkdir(parents=True, exist_ok=True)
            png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
            samples.append({"variant": variant, "slide": ordn,
                            "render": rel, "taskId": f"task-{variant}-{ordn}"})
    manifest = run / SAMPLES_REL
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({
        "schema": "style_samples_manifest/v1",
        "phase": "P-STYLE-PREVIEW (order 4.85)",
        "variants": list(variants),
        "representative_slides": list(REP_SLIDES),
        "samples": samples,
        "owner_pick_required": True,
        "owner_pick_artifact": CHOICE_REL,
    }, indent=2), encoding="utf-8")
    return run


def _record_pick(run: Path, variant: str = WINNER,
                 owner_msg_id: str = "owner-msg-42") -> subprocess.CompletedProcess:
    """The REAL recorder, in a child process, exactly as an agent runs it."""
    return subprocess.run(
        [sys.executable, str(DRIVER), "--run-dir", str(run),
         "--style-pick", variant, "--owner-msg-id", owner_msg_id],
        capture_output=True, text=True, timeout=180)


def _winner_renders(run: Path, variant: str = WINNER) -> list:
    doc = json.loads((run / SAMPLES_REL).read_text(encoding="utf-8"))
    return [row["render"] for row in doc["samples"] if row["variant"] == variant]


def _engine_auto_pick_choice(variant: str = WINNER) -> dict:
    """The exact shape Engine._style_pick_write_auto_choice writes: proof
    provenance, never an owner_msg_id, never a locked_renders field."""
    return {
        "owner_approved": True,
        "chosen_variant": variant,
        "auto_pick": True,
        "auto_pick_basis": "intake.style_pick_auto:true (recorded client "
                           "opt-in; the owner-response wait timed out)",
        "picked_at": "2026-11-12T21:00:00+00:00",
        "reason": "variant 1 auto-picked after the owner-response timeout "
                  "under a recorded intake.style_pick_auto opt-in",
    }


# ---------------------------------------------------------------------------
# A1 — the file the real driver writes passes the render check
# ---------------------------------------------------------------------------
def test_a_driver_recorded_pick_passes_the_render_check(tmp_path):
    run = _seed_run(tmp_path)
    proc = _record_pick(run)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    choice = json.loads((run / CHOICE_REL).read_text(encoding="utf-8"))
    # The premise of the finding, re-proved here: the recorder writes NO
    # locked_renders. If it ever starts writing one this test must change too.
    assert "locked_renders" not in choice
    assert choice["chosen_variant"] == WINNER

    assert bd._chk_style_preview(run) == "", (
        "a pick the one sanctioned recorder wrote is refused by the render "
        "check — AF-STYLE-DOUBLECHARGE is blocking every correctly recorded "
        "style pick again")


# ---------------------------------------------------------------------------
# A2 — the engine's auto-pick shape passes too
# ---------------------------------------------------------------------------
def test_the_engine_auto_pick_shape_passes_the_render_check(tmp_path):
    run = _seed_run(tmp_path)
    choice_path = run / CHOICE_REL
    choice_path.parent.mkdir(parents=True, exist_ok=True)
    choice_path.write_text(json.dumps(_engine_auto_pick_choice(), indent=2),
                           encoding="utf-8")
    assert bd._chk_style_preview(run) == ""


# ---------------------------------------------------------------------------
# A3 — control: a deleted winner render is still refused
# ---------------------------------------------------------------------------
def test_a_missing_winner_sample_render_is_still_refused(tmp_path):
    run = _seed_run(tmp_path)
    proc = _record_pick(run)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    victim = _winner_renders(run)[1]
    (run / victim).unlink()

    verdict = bd._chk_style_preview(run)
    assert verdict.startswith("AF-STYLE-DOUBLECHARGE"), verdict
    assert victim in verdict, (
        "the refusal must name the render that is gone, not a generic message")


def test_a_manifest_with_no_render_for_the_winner_is_still_refused(tmp_path):
    """The derived list must exist: a chosen variant the manifest never
    rendered is a real double-charge risk, so it keeps the refusal."""
    run = _seed_run(tmp_path)
    proc = _record_pick(run)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    doc = json.loads((run / SAMPLES_REL).read_text(encoding="utf-8"))
    doc["samples"] = [row for row in doc["samples"]
                      if row["variant"] != WINNER]
    (run / SAMPLES_REL).write_text(json.dumps(doc, indent=2), encoding="utf-8")

    verdict = bd._chk_style_preview(run)
    assert verdict.startswith("AF-STYLE-DOUBLECHARGE"), verdict


# ---------------------------------------------------------------------------
# A4 — control: no pick is still AF-STYLE-UNPICKED (never weakened)
# ---------------------------------------------------------------------------
def test_no_pick_is_still_refused_as_unpicked(tmp_path):
    run = _seed_run(tmp_path)
    verdict = bd._chk_style_preview(run)
    assert verdict.startswith("AF-STYLE-UNPICKED"), verdict


# ---------------------------------------------------------------------------
# The explicit locked_renders branch is unchanged
# ---------------------------------------------------------------------------
def test_an_explicit_locked_renders_list_is_used_as_before(tmp_path):
    run = _seed_run(tmp_path)
    locked = _winner_renders(run)
    choice_path = run / CHOICE_REL
    choice_path.parent.mkdir(parents=True, exist_ok=True)
    choice_path.write_text(json.dumps({
        "owner_approved": True,
        "chosen_variant": WINNER,
        "owner_msg_id": "owner-msg-42",
        "locked_renders": locked,
    }, indent=2), encoding="utf-8")
    assert bd._chk_style_preview(run) == ""

    (run / locked[0]).unlink()
    verdict = bd._chk_style_preview(run)
    assert verdict.startswith("AF-STYLE-DOUBLECHARGE"), verdict
    assert locked[0] in verdict, verdict


# ---------------------------------------------------------------------------
# A5 — the probe: NOT CONFIRMED, and the same instrument can still see a trap
# ---------------------------------------------------------------------------
def _probe(run: Path) -> str:
    """The probe the unit names, in miniature: it asks the production check and
    reports whether the trap is still there."""
    verdict = bd._chk_style_preview(run)
    if verdict == "":
        return "NOT CONFIRMED"
    if verdict.startswith("AF-STYLE-DOUBLECHARGE"):
        return "TRAP CONFIRMED"
    return f"OTHER: {verdict}"


def test_the_probe_reports_not_confirmed_and_still_discriminates(tmp_path):
    run = _seed_run(tmp_path)
    proc = _record_pick(run)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert _probe(run) == "NOT CONFIRMED"

    # Control on the same instrument: remove one winner render and the probe
    # must go back to TRAP CONFIRMED. A probe that cannot fail proves nothing.
    (run / _winner_renders(run)[0]).unlink()
    assert _probe(run) == "TRAP CONFIRMED"
