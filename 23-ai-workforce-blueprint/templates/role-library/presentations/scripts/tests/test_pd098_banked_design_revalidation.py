"""PD-TEST-098 (banked re-validation half) -- the design-page prompt must not
re-validate on hash identity alone (tests/test_pd098_banked_design_revalidation.py).

THE DEFECT. `Engine._revalidate_banked` (phases.py) re-validates every banked
artifact of a `done` phase on EVERY resume: pass -> SKIP and reuse the banked
work; fail -> `_checkpoint(status=PENDING, banked_invalid=[...])` and the phase
RE-RUNS. That is the engine's own self-healing path -- and it did not fire for
`prompts/<page>.design.txt`, because `validate_artifact` matched none of its
per-type arms and fell through to the F15 catch-all, which checks only
exists / non-empty / sha256 identity.

Measured read-only against the live run
pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4 (all three returned True
with "no per-type predicate, verified by recorded hash"):

    prompts/sales.design.txt    58,484 bytes
    prompts/checkout.design.txt 49,526 bytes
    prompts/vsl.design.txt      51,334 bytes

Three prompts the paid render gate MUST refuse (2.7x-3.2x the 18,000-char
ceiling) re-validated clean, so the three design phases stayed `done`, and the
refusal surfaced two phases later at P-U-DESIGN-RENDER-*. Nothing re-authored.

THE FIX. A per-type arm for `prompts/*.design.txt`, beside the existing
`working/prompts/slide-NN.txt -> validate_text(path, _PROMPT_FLOOR)` precedent,
enforcing the SAME band the render gate enforces, READ FROM `prompt_gate` (never
re-typed). With it the next resume returns banked_invalid for the three design
phases, the engine resets them to PENDING, and the (now band-aware) producer
re-authors them inside the shared budget.

WHAT THESE TESTS PIN
  1. An over-ceiling design prompt FAILS re-validation with a named AF-P2
     reason (the live 58,484-char shape).
  2. A sub-floor design prompt FAILS with a named AF-P1 reason.
  3. An in-band design prompt still PASSES, and the sha256 contract still
     applies (a mismatch still fails).
  4. The band is READ FROM prompt_gate -- moving the gate's constants moves
     this predicate, so there is no second copy to drift.
  5. BLAST RADIUS: every NON-design artifact re-validates EXACTLY as before,
     verdict AND reason string (frozen from pre-fix behaviour), so the new arm
     is provably additive.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # cross-test fixture import

import prompt_gate as PG  # noqa: E402
from presentation_job import artifacts as A  # noqa: E402

# The three live artifacts, by their measured sizes.
LIVE_SIZES = {"sales": 58484, "checkout": 49526, "vsl": 51334}


class _Manifest:
    """Manifest stub: one registered deliverable, so the deliverables arm is
    reachable in the blast-radius table."""
    deliverables = [{"filename": "PRESENTER-GUIDE.pdf", "min_bytes": 51200}]


def _run(tmp_path: Path) -> Path:
    rd = tmp_path / "run"
    for d in ("working/research", "working/qc", "working/copy",
              "working/prompts", "prompts", "working/deliverables"):
        (rd / d).mkdir(parents=True, exist_ok=True)
    return rd


def _write(rd: Path, rel: str, text: str) -> str:
    p = rd / rel
    p.write_text(text, encoding="utf-8")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _validate(rd: Path, rel: str, sha=None):
    return A.validate_artifact(rd, rel, _Manifest(), recorded_sha=sha)


def _gate_clean(size: int) -> str:
    """A prompt of exactly `size` chars that clears the WHOLE gate, not just the
    band. The in-band controls below assert "reusable banked work", and since
    PD-TEST-113/D2 the banked predicate applies the same gate the render phase
    applies -- so a byte-padded fixture (`"d" * size`) is refused for the RIGHT
    reason (1 distinct word against a 220 floor). Reused from the sibling suite
    rather than duplicated, so the two cannot drift."""
    from test_pd098_design_verifier_band import _gate_clean_prompt
    return _gate_clean_prompt(size)


# ---------------------------------------------------------------------------
# 1 / 2 / 3 -- the predicate's own behaviour.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("page,size", sorted(LIVE_SIZES.items()))
def test_over_ceiling_design_prompt_fails_revalidation(tmp_path, page, size):
    """The measured live shape must NOT be reusable banked work: this is the
    assertion whose absence kept the three design phases `done`."""
    rd = _run(tmp_path)
    rel = f"prompts/{page}.design.txt"
    sha = _write(rd, rel, "d" * size)
    ok, why = _validate(rd, rel, sha)
    assert not ok, "an over-ceiling design prompt must not re-validate"
    assert "AF-P2" in why and str(PG.PROMPT_CHAR_CEILING) in why, why
    assert f"{size} chars" in why
    # ...and the render gate agrees, so the two can never disagree about it.
    assert any("AF-P2" in p for p in PG.prompt_problems((rd / rel).read_text()))


def test_under_floor_design_prompt_fails_revalidation(tmp_path):
    rd = _run(tmp_path)
    rel = "prompts/vsl.design.txt"
    sha = _write(rd, rel, "d" * (PG.PROMPT_CHAR_FLOOR - 1))
    ok, why = _validate(rd, rel, sha)
    assert not ok and "AF-P1" in why and str(PG.PROMPT_CHAR_FLOOR) in why, why


def test_in_band_design_prompt_passes_and_sha_still_applies(tmp_path):
    rd = _run(tmp_path)
    rel = "prompts/checkout.design.txt"
    sha = _write(rd, rel, _gate_clean(PG.PROMPT_CHAR_CEILING))
    ok, why = _validate(rd, rel, sha)
    assert ok, why
    assert "shared prompt band" in why and "sha256 match" in why

    ok, why = _validate(rd, rel, "0" * 64)
    assert not ok and "sha256 mismatch" in why, why


def test_all_three_design_pages_are_covered():
    for page in ("sales", "checkout", "vsl"):
        assert A._DESIGN_PROMPT_RE.match(f"prompts/{page}.design.txt"), page
    # A near-miss must NOT be swept into the band arm.
    for other in ("working/prompts/sales.design.txt", "prompts/sales.design.md",
                  "prompts/sales.txt", "prompts/SALES.DESIGN.TXT".lower() + "x"):
        assert not A._DESIGN_PROMPT_RE.match(other), other


# ---------------------------------------------------------------------------
# 4 -- the band is READ FROM prompt_gate, never re-typed.
# ---------------------------------------------------------------------------
def test_band_is_read_from_prompt_gate_not_hardcoded(tmp_path, monkeypatch):
    rd = _run(tmp_path)
    rel = "prompts/sales.design.txt"
    _write(rd, rel, _gate_clean(30000))   # over 18000, under a moved ceiling
    assert not _validate(rd, rel)[0]

    monkeypatch.setattr(PG, "PROMPT_CHAR_CEILING", 40000)
    monkeypatch.setattr(PG, "PROMPT_CHAR_FLOOR", 20000)
    ok, why = _validate(rd, rel)
    assert ok, (
        "the predicate followed a monkeypatched prompt_gate ceiling, so the "
        f"band is imported, not hard-coded: {why}")


def test_predicate_degrades_loudly_when_prompt_gate_is_unavailable(tmp_path, monkeypatch):
    """A broken install must not turn every banked design prompt into a
    permanent re-author loop -- but the degrade must be DISCLOSED, never passed
    off as a real band check."""
    rd = _run(tmp_path)
    rel = "prompts/sales.design.txt"
    _write(rd, rel, "d" * 58484)
    monkeypatch.setattr(A, "_PROMPT_GATE_CACHE", None)
    monkeypatch.setattr(A, "_PROMPT_GATE_TRIED", True)
    ok, why = A.validate_artifact(rd, rel, _Manifest(), recorded_sha=None)
    assert ok, "the fallback keeps pre-fix behaviour rather than looping"
    assert "BAND PREDICATE UNAVAILABLE" in why and "NOT checked" in why, why


# ---------------------------------------------------------------------------
# 5 -- BLAST RADIUS: additive, no pre-existing arm moves.
# ---------------------------------------------------------------------------
def test_non_design_artifacts_revalidate_exactly_as_before(tmp_path):
    """Frozen pre-fix verdicts (captured by running this same table against
    `origin/main`'s artifacts.py). Verdict AND reason must be identical, so the
    new arm can only take paths that previously reached the F15 catch-all."""
    rd = _run(tmp_path)
    sha_md = _write(rd, "working/research/brief-generated.md",
                    "# brief\n" + "real research text. " * 300)
    sha_json = _write(rd, "working/qc/copy_qc_report.json", json.dumps(
        {"gate": "Phase 1Q", "criteria": [], "average": 9.0, "pass": True}))
    sha_slides = _write(rd, "working/copy/slides.json", json.dumps(
        {"slides": [{"ordinal": n} for n in range(1, 9)]}))
    sha_slide = _write(rd, "working/prompts/slide-07.txt", "s" * 12000)
    sha_bin = _write(rd, "mystery.bin", "\x00\x01")
    sha_empty = _write(rd, "empty.txt", "")

    # (rel, recorded_sha, expected_ok, expected_substring) -- FROZEN pre-fix.
    table = [
        ("working/research/brief-generated.md", sha_md, True,
         "no per-type predicate, verified by recorded hash"),
        ("working/qc/copy_qc_report.json", sha_json, True, "ok (valid JSON"),
        ("working/copy/slides.json", sha_slides, True,
         "no per-type predicate, verified by recorded hash"),
        ("working/prompts/slide-07.txt", sha_slide, True,
         "ok (12000 bytes, floor 9000)"),
        ("mystery.bin", sha_bin, True,
         "no per-type predicate, verified by recorded hash"),
        # Both halves of the F15 branch: with NO recorded sha it refuses on
        # identity-of-predicate grounds; with one it refuses on emptiness.
        ("empty.txt", None, False,
         "no validity predicate for empty.txt"),
        ("empty.txt", sha_empty, False, "is empty (0 bytes)"),
        ("working/research/absent.md", None, False,
         "no validity predicate for working/research/absent.md"),
    ]
    for rel, sha, want_ok, want_why in table:
        ok, why = _validate(rd, rel, sha)
        assert ok is want_ok, f"{rel}: verdict moved ({ok} != {want_ok}): {why}"
        assert want_why in why, f"{rel}: reason moved: {why}"


def test_deliverable_arm_precedence_is_preserved(tmp_path):
    """The new arm sits AFTER the deliverables loop, so a path a manifest
    declares as a deliverable still takes the deliverable arm first -- the new
    branch can only take files that previously fell to the F15 catch-all."""
    rd = _run(tmp_path)
    rel = "prompts/sales.design.txt"
    sha = _write(rd, rel, "d" * 58484)

    class Declared:
        deliverables = [{"filename": "sales.design.txt", "min_bytes": 10}]

    ok, why = A.validate_artifact(rd, rel, Declared(), recorded_sha=sha)
    assert ok, "the deliverable arm still wins for a declared deliverable"
    assert "no per-type predicate" not in why  # it took the .txt deliverable arm


def test_non_design_prompt_paths_do_not_enter_the_band_arm(tmp_path):
    """The near-miss paths must keep their pre-fix behaviour exactly."""
    rd = _run(tmp_path)
    sha = _write(rd, "working/prompts/sales.design.txt", "d" * 58484)
    ok, why = _validate(rd, "working/prompts/sales.design.txt", sha)
    assert ok and "no per-type predicate" in why, why


# ---------------------------------------------------------------------------
# 6 -- END TO END through the REAL Engine._revalidate_banked and the REAL
#      Manifest. This is the acceptance target: the engine's own resume
#      self-heal must fire on the three live design prompts.
# ---------------------------------------------------------------------------
def _find_shipped_manifest():
    """Locate the shipped PIPELINE-MANIFEST.json by WALKING UP from this file,
    never by a fixed `parents[N]` index: `SCRIPTS.parents[4]` raised
    `IndexError: 4` at COLLECTION time in any tree shallower than the canonical
    checkout (a deployed copy, a scratch clone), turning the whole module into a
    collection error rather than a skip."""
    for base in SCRIPTS.parents:
        cand = base / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
    return None


_REAL_MANIFEST = _find_shipped_manifest()

# The REAL phase -> artifact bindings (PIPELINE-MANIFEST.json v69), and the
# measured live artifact sizes.
# (phase, artifact, live BYTE size, live STRIPPED length) -- both measured
# read-only on the live files; the engine measures the stripped length.
DESIGN_PHASE_ARTIFACTS = (
    ("P-U-DESIGN-SALES", "prompts/sales.design.txt", 58484, 58482),
    ("P-U-DESIGN-CHECKOUT", "prompts/checkout.design.txt", 49526, 49525),
    ("P-U-DESIGN-VSL", "prompts/vsl.design.txt", 51334, 51333),
)


def _real_bindings_match_the_shipped_manifest():
    """When the shipped manifest is in this tree, the bindings above must be
    exactly what it declares -- so this fixture cannot drift from the real
    contract it is standing in for."""
    if _REAL_MANIFEST is None:
        return None
    m = json.loads(_REAL_MANIFEST.read_text(encoding="utf-8"))
    got = {}
    for ph in m.get("phases", []):
        rel = ph.get("produces_artifact")
        if isinstance(rel, list) and rel:
            rel = rel[0]
        if isinstance(rel, str):
            got[ph["id"]] = rel
    return {pid: got.get(pid) for pid, _r, _b, _s in DESIGN_PHASE_ARTIFACTS}


def _design_engine(tmp_path, stripped_override=None):
    """A REAL Engine + REAL Manifest over a scratch run dir holding design
    prompts at the live sizes, with their real sha256 recorded as banked --
    which is precisely the state the live run is in.

    The manifest is the SHIPPED `PIPELINE-MANIFEST.json` whenever this tree has
    it; the inline fixture is only a fallback for a tree that ships without it,
    and its bindings are pinned to the shipped manifest by
    `test_fixture_bindings_match_the_shipped_manifest`."""
    from presentation_job.manifest import Manifest
    from presentation_job.phases import Engine
    from presentation_job.state import StateStore

    rd = tmp_path / "run"
    (rd / "prompts").mkdir(parents=True, exist_ok=True)
    phases = []
    for pid, rel, nbytes, nstripped in DESIGN_PHASE_ARTIFACTS:
        p = rd / rel
        if stripped_override is not None:
            p.write_text(_gate_clean(stripped_override), encoding="utf-8")
        else:
            # Reproduce the live file's exact byte size AND stripped length.
            p.write_text("d" * nstripped + "\n" * max(0, nbytes - nstripped),
                         encoding="utf-8")
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        phases.append({"id": pid, "status": "done", "artifacts": [rel],
                       "sha256": {rel: sha}, "attempts": 1, "heal_events": [],
                       "attested_at": "x"})
    if _REAL_MANIFEST is not None:
        manifest = Manifest(_REAL_MANIFEST)
    else:
        mf = tmp_path / "mf.json"
        mf.write_text(json.dumps({
            "manifest_version": 69,
            "phases": [{"id": pid, "order": 4.2 + i,
                        "owning_role": "slide-image-creator",
                        "produces_artifact": [rel], "client_report": {},
                        "executor": {"kind": "agent"}}
                       for i, (pid, rel, _b, _s) in enumerate(DESIGN_PHASE_ARTIFACTS)],
            "deliverables_required": [],
        }))
        manifest = Manifest(mf)
    store = StateStore(rd)
    store.save({"job_id": "pj", "schema_version": 1, "run_dir": str(rd),
                "phases": phases, "events": [], "sent": {},
                "requester": {"chat_id": "t"}, "heartbeat": {}})
    return Engine(rd, manifest, store, store.load(), dry_run=True), manifest


@pytest.mark.parametrize("pid,rel,nbytes,nstripped", DESIGN_PHASE_ARTIFACTS)
def test_revalidate_banked_rejects_the_live_over_ceiling_design_prompt(
        tmp_path, pid, rel, nbytes, nstripped):
    """THE ACCEPTANCE TARGET (PD-TEST-104's proven chain): with the REAL banked
    sha256 recorded, the REAL Engine._revalidate_banked must return a NON-EMPTY
    reason for the design phase -- naming AF-P2 and the measured length -- so
    `run_phase` checkpoints it back to PENDING and the engine re-authors it.

    Pre-fix this returned an EMPTY list ("no per-type predicate, verified by
    recorded hash"), which is why all three phases stayed `done` and the
    refusal surfaced two phases later at the paid render gate."""
    eng, manifest = _design_engine(tmp_path)
    bad = eng._revalidate_banked(manifest.phase(pid), eng._phase_state(pid))
    assert bad, (
        f"{pid}: hash identity alone still let an over-ceiling design prompt "
        "re-validate clean")
    joined = " ".join(bad)
    assert "AF-P2" in joined, joined
    assert str(nstripped) in joined.replace(",", ""), joined
    assert rel in joined


@pytest.mark.parametrize("pid,rel,nbytes,nstripped", DESIGN_PHASE_ARTIFACTS)
def test_run_phase_marks_the_banked_design_prompt_invalid(
        tmp_path, pid, rel, nbytes, nstripped):
    """The engine's OWN self-heal path must engage: `run_phase` emits
    `phase.banked_invalid` and records the reason on the phase state, which is
    what resets it to PENDING and re-runs it on resume."""
    eng, manifest = _design_engine(tmp_path)
    eng.run_phase(manifest.phase(pid))
    kinds = [e.get("kind") for e in eng.state.get("events", [])]
    assert "phase.banked_invalid" in kinds, kinds
    assert eng._phase_state(pid).get("banked_invalid"), (
        f"{pid}: banked_invalid was not recorded, so the phase would not re-run")


def test_revalidate_banked_accepts_an_in_band_design_prompt(tmp_path):
    """NEGATIVE CONTROL -- without this, the test above would pass even if the
    predicate simply failed everything, and every resume would re-author
    forever."""
    eng, manifest = _design_engine(tmp_path,
                                   stripped_override=PG.PROMPT_CHAR_CEILING)
    for pid, rel, _b, _s in DESIGN_PHASE_ARTIFACTS:
        bad = eng._revalidate_banked(manifest.phase(pid), eng._phase_state(pid))
        assert bad == [], f"{pid}: an in-band design prompt must reuse banked work: {bad}"


def test_fixture_bindings_match_the_shipped_manifest():
    """The fixtures above stand in for the real manifest; when it is present,
    prove they still match it."""
    got = _real_bindings_match_the_shipped_manifest()
    if got is None:
        pytest.skip("PIPELINE-MANIFEST.json not present in this tree")
    for pid, rel, _b, _s in DESIGN_PHASE_ARTIFACTS:
        assert got[pid] == rel, f"{pid} binding drifted: {got[pid]} != {rel}"


def test_engine_binding_cannot_silently_detach_from_the_predicate():
    """`phases.py` does `from .artifacts import validate_artifact`, so
    `_revalidate_banked` calls the SAME function object this module's arm lives
    in. A future refactor that rebinds the name (or re-imports it into a
    wrapper that skips the arm) would silently detach PD-TEST-098 from the
    resume path while leaving these unit tests green -- this assertion makes
    that refactor fail loudly instead."""
    from presentation_job import artifacts as _a
    from presentation_job import phases as _p
    assert _p.validate_artifact is _a.validate_artifact, (
        "the engine's validate_artifact is no longer the function carrying the "
        "PD-TEST-098 design-prompt band arm")
    import inspect
    assert "_DESIGN_PROMPT_RE" in inspect.getsource(_p.validate_artifact), (
        "the engine's validate_artifact no longer reaches the design-prompt arm")
