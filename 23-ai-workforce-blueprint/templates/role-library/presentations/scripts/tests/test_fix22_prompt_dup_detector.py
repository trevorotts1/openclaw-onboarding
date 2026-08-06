"""Tests for FIX-22 — canonical zero-padded prompt files + duplicate detector.

Bar (Gauntlet Loop FIX-22 / T-20 / D16):
  * a 20-slide prompt set generates EXACTLY 20 canonical zero-padded
    slide-%02d.txt files (no slide-1.txt twins);
  * seeding a conflicting `slide-1.txt` beside `slide-01.txt` makes the
    duplicate detector FAIL (AF-PROMPT-DUP-FILE), both in the shared
    prompt_gate detector AND in every enforcement path that consumes the
    prompt dir (build_deck preflight / prompt-QC teeth, presentation_job
    close-out gate, prove_pres_prompt_floor --dir);
  * a non-canonical `slide-100.txt` / `slide-1.txt` name fails AF-PROMPT-NAME.

No network, no credentials. Stdlib + pytest/tmp_path only — the detector must
run identically on a deployed client box.
"""

import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import prompt_gate as pg  # noqa: E402
import prove_pres_prompt_floor as prov  # noqa: E402


def _write_canonical_set(prompts: pathlib.Path, n: int = 20) -> list:
    """Write n canonical zero-padded slide-%02d.txt files. Returns the sorted
    name list. Content is a genuinely-rich prompt so per-file gating also passes."""
    rich = prov._rich_pass_prompt()
    names = []
    for i in range(1, n + 1):
        f = prompts / f"slide-{i:02d}.txt"
        f.write_text(rich)
        names.append(f.name)
    return sorted(names)


# ---------------------------------------------------------------------------
# prompt_gate detector (the single source of truth)
# ---------------------------------------------------------------------------

def test_20_canonical_files_are_clean(tmp_path):
    """Exactly 20 zero-padded slide-%02d.txt files -> no problems, count == 20,
    no duplicates, no non-canonical names."""
    d = tmp_path / "working" / "prompts"
    d.mkdir(parents=True)
    names = _write_canonical_set(d, 20)
    assert names == [f"slide-{i:02d}.txt" for i in range(1, 21)], names

    problems = pg.prompt_dir_problems(d)
    assert problems == [], f"20 canonical files must be clean, got {problems}"

    rep = pg.scan_prompt_dir(d)
    assert rep["count"] == 20, rep
    assert rep["duplicates"] == [], rep
    assert rep["non_canonical"] == [], rep
    assert len(rep["canonical"]) == 20, rep


def test_seeded_slide1_txt_duplicate_fires(tmp_path):
    """The D16 collision: slide-01.txt AND slide-1.txt both target slide 1. The
    detector must FAIL (AF-PROMPT-DUP-FILE naming slide 1 and both files)."""
    d = tmp_path / "working" / "prompts"
    d.mkdir(parents=True)
    _write_canonical_set(d, 20)
    # Seed the conflicting non-canonical twin exactly as D16 describes.
    rich = prov._rich_pass_prompt()
    (d / "slide-1.txt").write_text(rich)

    problems = pg.prompt_dir_problems(d)
    dup = [p for p in problems if "AF-PROMPT-DUP-FILE" in p]
    assert dup, f"duplicate detector must fire, got {problems}"
    assert "slide 1" in dup[0], dup[0]
    assert "slide-01.txt" in dup[0] and "slide-1.txt" in dup[0], dup[0]

    rep = pg.scan_prompt_dir(d)
    assert len(rep["targets"].get(1, [])) == 2, rep["targets"]
    assert "slide-1.txt" in rep["non_canonical"], rep
    assert "slide-1.txt" in rep["duplicates"], rep


def test_non_canonical_three_digit_name_fires(tmp_path):
    """slide-100.txt (3-digit, not %02d) is a non-canonical prompt filename and
    must fail AF-PROMPT-NAME even without a same-target twin present."""
    d = tmp_path / "working" / "prompts"
    d.mkdir(parents=True)
    _write_canonical_set(d, 3)
    (d / "slide-100.txt").write_text("z" * 9500)

    problems = pg.prompt_dir_problems(d)
    name = [p for p in problems if "AF-PROMPT-NAME" in p and "slide-100" in p]
    assert name, f"AF-PROMPT-NAME must fire on slide-100.txt, got {problems}"


def test_missing_prompt_dir_returns_clean():
    """A missing prompts dir is not a duplicate-detector defect — the caller owns
    the 'no prompts dir' case, so the detector must return [] (not raise)."""
    import tempfile
    problems = pg.prompt_dir_problems(pathlib.Path(tempfile.mkdtemp()) / "nope")
    assert problems == []


# ---------------------------------------------------------------------------
# enforcement paths that must fail closed on the seeded conflict
# ---------------------------------------------------------------------------

def test_build_deck_preflight_fails_on_duplicate(tmp_path):
    """_chk_rich_prompts / _collect_prompt_problems must FAIL closed on a
    slide-1.txt vs slide-01.txt collision (the D16 defect)."""
    import build_deck as bd

    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "prompts").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text(
        '[' + ",".join(f'{{"slide": {i}, "scene": "x", "copy": ["y"]}}'
                       for i in range(1, 21)) + ']')
    _write_canonical_set(rd / "working" / "prompts", 20)
    rich = prov._rich_pass_prompt()
    (rd / "working" / "prompts" / "slide-1.txt").write_text(rich)

    collected = bd._collect_prompt_problems(rd)
    assert collected and collected[0][0] < 0, collected  # dir-level fatal sentinel
    reason = bd._chk_rich_prompts(rd)
    assert "AF-PROMPT-DUP-FILE" in reason, reason
    teeth = bd.check_prompt_qc_teeth(rd)
    assert "AF-PROMPT-DUP-FILE" in teeth, teeth


def test_closeout_gate_fails_on_duplicate(tmp_path):
    """presentation_job Gates._prompt_floor_gate must fail closed on the seeded
    conflict, so a job can never close DONE over a broken prompt set."""
    from presentation_job.gates import Gates

    rd = tmp_path / "run"
    d = rd / "working" / "prompts"
    d.mkdir(parents=True)
    _write_canonical_set(d, 20)
    rich = prov._rich_pass_prompt()
    (d / "slide-1.txt").write_text(rich)

    g = Gates(rd, {})._prompt_floor_gate()
    assert g["state"] == "fail", g
    assert "AF-PROMPT-DUP-FILE" in g.get("reason", ""), g

    # Control: remove the twin -> the same gate passes on the canonical set.
    (d / "slide-1.txt").unlink()
    g2 = Gates(rd, {})._prompt_floor_gate()
    assert g2["state"] == "pass", g2


def test_prover_dir_fails_on_duplicate(tmp_path):
    """prove_pres_prompt_floor.py --dir must exit EXIT_VIOLATION(2) when the dir
    holds a slide-1.txt vs slide-01.txt collision."""
    rd = tmp_path / "run"
    d = rd / "working" / "prompts"
    d.mkdir(parents=True)
    _write_canonical_set(d, 20)
    rich = prov._rich_pass_prompt()
    (d / "slide-1.txt").write_text(rich)

    rc = prov.main(["--dir", str(rd)])
    assert rc == prov.EXIT_VIOLATION, f"prover must exit {prov.EXIT_VIOLATION} on dup, got {rc}"

    # Control: clean dir exits 0.
    (d / "slide-1.txt").unlink()
    rc2 = prov.main(["--dir", str(rd)])
    assert rc2 == prov.EXIT_OK, f"clean prover dir must exit 0, got {rc2}"
