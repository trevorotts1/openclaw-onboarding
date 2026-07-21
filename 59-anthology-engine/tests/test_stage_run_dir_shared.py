#!/usr/bin/env python3
"""test_stage_run_dir_shared.py -- one durable run directory across the authoring stages.

THE DEFECT THIS CLOSES (T2-05):

Every stage dispatcher resolved its OWN working directory:

    d = SKILL_DIR / "state" / "runs" / STAGE / safe        # s0, s1, s2, ... s8

and each then handed that directory to the downstream authoring core:

    bash 54-anthology-writer/anthology-entry.sh --run-dir <that dir> --upto <PHASE>

54-anthology-writer/run_anthology.py::run() walks PHASE_ORDER from P0-INTAKE on
EVERY invocation and fails closed at the first phase whose required preflight
checker rejects the run dir. The artifacts those early gates need --
working/intake.json (written only by stage_s1_avatar._write_intake_bridge) and
working/avatar.md (written by the S1 Layer-1 call) -- landed in the S1 directory.
So a normal S2 dispatch handed Skill 54 an EMPTY directory and stopped at
P0-INTAKE, before tone authoring ever began. Same for every later stage.

THE FIX: one canonical per-participant directory,
`SKILL_DIR/state/runs/participants/<safe_key>`, resolved identically by s0..s8,
and read by stage_s9_assembly.participant_chapter_path().

WHAT THIS FILE PROVES (hermetic; every stage's SKILL_DIR is redirected into a
tempdir, so nothing is written inside the checkout, and no network is used):

  T1  all nine authoring dispatchers resolve the SAME directory for one key
  T2  ...and it is the canonical literal, not a stage-scoped one
  T3  S1's REAL intake bridge writes into the directory S2 hands off
  T4  Skill 54's REAL first gate (run_anthology._chk_intake) PASSES on that
      directory -- and still FAILS on a directory that lacks the artifact, so
      the gate has been observed failing, not only passing
  T5  S9 reads the frozen chapter from exactly where S5 and S6 write it

Run: python3 -m pytest 59-anthology-engine/tests/test_stage_run_dir_shared.py -q
 or: python3 59-anthology-engine/tests/test_stage_run_dir_shared.py
"""
import importlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
RUN_ANTHOLOGY = REPO_ROOT / "54-anthology-writer" / "run_anthology.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Every dispatcher that resolves a PER-PARTICIPANT run directory. stage_s9_assembly
# is deliberately absent: its own run dir is keyed by ANTHOLOGY id and must keep
# matching gate_engine.py::_s9_run_dir. S9 appears below in T5 as the READER of the
# per-participant chapter.
AUTHORING_STAGES = [
    "stage_s0_intake", "stage_s1_avatar", "stage_s2_tone", "stage_s3_title",
    "stage_s4_outline", "stage_s5_chapter", "stage_s6_rewrite", "stage_s7_cover",
    "stage_s8_deliver",
]

KEY = "cid-000111::ANTH-TESTKEY"
SAFE = "cid-000111__ANTH-TESTKEY"


def _load_stage(name):
    return importlib.import_module(name)


def _load_run_anthology():
    spec = importlib.util.spec_from_file_location("aw_run_anthology_under_test", RUN_ANTHOLOGY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Redirected:
    """Point every stage module's SKILL_DIR at a tempdir for the duration, so the
    real directory-resolution code runs but writes nothing inside the checkout."""

    def __init__(self, names):
        self.names = names
        self.mods = {}
        self.saved = {}

    def __enter__(self):
        self.tmpobj = tempfile.TemporaryDirectory(prefix="anth_rundir_")
        self.root = Path(self.tmpobj.name)
        for n in self.names:
            m = _load_stage(n)
            self.mods[n] = m
            self.saved[n] = m.SKILL_DIR
            m.SKILL_DIR = self.root
        return self

    def __exit__(self, *exc):
        for n, m in self.mods.items():
            m.SKILL_DIR = self.saved[n]
        self.tmpobj.cleanup()
        return False


# --------------------------------------------------------------------------- #
def test_every_authoring_stage_resolves_one_directory():
    with _Redirected(AUTHORING_STAGES) as env:
        resolved = {n: Path(env.mods[n]._run_dir_for(KEY)) for n in AUTHORING_STAGES}
        distinct = sorted({str(p) for p in resolved.values()})
        assert len(distinct) == 1, (
            "the authoring stages resolve %d different working directories for one "
            "participant key; a later stage cannot read what an earlier one wrote:\n  %s"
            % (len(distinct), "\n  ".join(distinct)))


def test_the_shared_directory_is_the_canonical_literal():
    with _Redirected(["stage_s1_avatar"]) as env:
        got = Path(env.mods["stage_s1_avatar"]._run_dir_for(KEY))
        want = env.root / "state" / "runs" / "participants" / SAFE
        assert got == want, "expected %s, got %s" % (want, got)
        assert (got / "working").is_dir(), "the resolver must create working/"


def test_s1_intake_bridge_lands_where_s2_hands_off():
    with _Redirected(["stage_s1_avatar", "stage_s2_tone"]) as env:
        s1, s2 = env.mods["stage_s1_avatar"], env.mods["stage_s2_tone"]
        d1 = s1._run_dir_for(KEY)
        s1._write_intake_bridge(
            d1,
            {"first_name": "Ada", "last_name": "Nkemdirim", "chapter_about": "a premise"},
            {"name": "First Light"},
        )
        d2 = Path(s2._run_dir_for(KEY))
        f = d2 / "working" / "intake.json"
        assert f.is_file(), (
            "S2 hands 54-anthology-writer a directory with no working/intake.json; "
            "S1 wrote it to %s" % d1)
        payload = json.loads(f.read_text(encoding="utf-8"))
        assert payload["anthology_title"] == "First Light"
        assert payload["chapter_premise"] == "a premise"


def test_skill54_first_gate_passes_on_the_shared_dir_and_fails_without_it():
    """The REAL downstream gate, driven in both directions."""
    aw = _load_run_anthology()
    with _Redirected(["stage_s1_avatar", "stage_s2_tone"]) as env:
        s1, s2 = env.mods["stage_s1_avatar"], env.mods["stage_s2_tone"]
        s1._write_intake_bridge(
            s1._run_dir_for(KEY),
            {"first_name": "Ada", "last_name": "Nkemdirim", "chapter_about": "a premise"},
            {"name": "First Light"},
        )
        ok, msg = aw._chk_intake(Path(s2._run_dir_for(KEY)))
        assert ok, "Skill 54's P0-INTAKE gate rejected the S2 run dir: %s" % msg

        # The other direction: the gate must still FAIL where the artifact is absent.
        empty = env.root / "state" / "runs" / "participants" / "no-such-participant"
        (empty / "working").mkdir(parents=True, exist_ok=True)
        bad_ok, bad_msg = aw._chk_intake(empty)
        assert not bad_ok, "P0-INTAKE passed a run dir with no working/intake.json"
        assert "intake.json" in bad_msg, bad_msg


def test_s9_reads_the_chapter_where_s5_and_s6_write_it():
    with _Redirected(["stage_s5_chapter", "stage_s6_rewrite", "stage_s9_assembly"]) as env:
        s5, s6, s9 = (env.mods["stage_s5_chapter"], env.mods["stage_s6_rewrite"],
                      env.mods["stage_s9_assembly"])
        s5_chapter = Path(s5._run_dir_for(KEY)) / "working" / "chapter.md"
        s6_chapter = Path(s6._run_dir_for(KEY)) / "working" / "chapter.md"
        s9_chapter = Path(s9.participant_chapter_path(KEY))
        assert s5_chapter == s6_chapter == s9_chapter, (
            "S9 does not read the chapter where the authoring stages write it:\n"
            "  S5 writes %s\n  S6 writes %s\n  S9 reads  %s" % (s5_chapter, s6_chapter, s9_chapter))
        s5_chapter.write_bytes(b"# A frozen chapter\n")
        assert s9_chapter.read_bytes() == b"# A frozen chapter\n"


TESTS = [
    test_every_authoring_stage_resolves_one_directory,
    test_the_shared_directory_is_the_canonical_literal,
    test_s1_intake_bridge_lands_where_s2_hands_off,
    test_skill54_first_gate_passes_on_the_shared_dir_and_fails_without_it,
    test_s9_reads_the_chapter_where_s5_and_s6_write_it,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print("  PASS: %s" % t.__name__)
        except AssertionError as exc:
            failed += 1
            print("  FAIL: %s\n        %s" % (t.__name__, exc))
        except Exception as exc:  # noqa: BLE001 — a crash is a failure, reported as one
            failed += 1
            print("  ERROR: %s\n        %r" % (t.__name__, exc))
    print("\n=== %d passed, %d failed ===" % (len(TESTS) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
