#!/usr/bin/env python3
"""S75-005 (U-A02): the research stage contract names what the stage really is.

The defect this pins: ``STAGE_DESCRIPTORS["research"]`` published a recovery
command carrying ``--governed`` (an option ``research.py`` never defines) and an
artifact inventory -- ``research/receipt.json``, ``research/claims.json``,
``research/captures.json`` -- that no module writes. ``research.render()``
writes ``research/evidence.json``, ``research/manifest.json`` and
``research/bundle.json`` (research.py 292, 305-319); those are the three the
descriptor must declare.

Proved here, against the real runner and the real fixture brief:

  * the descriptor command, with the run dir substituted, is accepted by
    research.py's own parser and runs to exit 0;
  * the descriptor recovery command is accepted the same way and names no
    option the runner does not define (no ``--governed``);
  * after that real run every declared artifact exists and is non-empty;
  * every stage's script answers its own ``--help`` -- the step-5 check, and a
    negative control showing that check really discriminates.

Offline: ``--no-gather`` is passed and the fixture brief carries its own
sources, so no network is touched. Writes only inside a local temp dir.
"""
import contextlib
import io
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                     # 75-drama-song-ad-factory/
CORE = ROOT / "scripts" / "core"
RESEARCH = CORE / "research_engine"
FIXTURE = RESEARCH / "fixtures" / "research_claims.json"

sys.path[:0] = [str(RESEARCH), str(CORE), str(HERE)]

from intake_preflight import factory      # noqa: E402
import research as R                      # noqa: E402

#: S75-005: the files research.render() writes unconditionally. Pinned here so
#: a drift back to invented names fails by name.
REAL_ARTIFACTS = ("research/evidence.json", "research/manifest.json",
                  "research/bundle.json")


def _args_after_script(command, run_dir):
    """The descriptor's arguments after its interpreter and script, with the
    ``{RUN}`` / ``$RUN`` placeholder replaced by the real run dir."""
    tokens = shlex.split(str(command or ""))
    if tokens and tokens[0] in factory._INTERPRETERS:
        tokens = tokens[1:]
    if tokens and Path(tokens[0]).name == "research.py":
        tokens = tokens[1:]
    out = []
    for tok in tokens:
        out.append(tok.replace("{RUN}", str(run_dir)).replace("$RUN", str(run_dir)))
    return out


def _run_main(argv):
    """research.main with its JSON envelope captured. Returns (code, output)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = R.main(argv)
    return code, buf.getvalue()


class ResearchStageContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="s75-005-")
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.brief = self.run_dir / "brief.json"
        self.brief.write_text(json.dumps(fixture["accept"], indent=2),
                              encoding="utf-8")
        self.d = factory.STAGE_DESCRIPTORS["research"]

    # ---------------------------------------------------------- the inventory

    def test_descriptor_declares_the_files_the_stage_really_writes(self):
        self.assertEqual(tuple(self.d["artifacts"]), REAL_ARTIFACTS,
                         "descriptor artifacts drifted from research.render()")

    def test_every_declared_artifact_exists_and_is_non_empty_after_a_real_run(self):
        code, out = _run_main(["--brief", str(self.brief),
                               "--outdir", str(self.run_dir), "--no-gather"])
        self.assertEqual(code, R.EXIT["ok"], out)
        for rel in self.d["artifacts"]:
            path = self.run_dir / rel
            self.assertTrue(path.is_file(), "%s was not written: %s" % (rel, out))
            self.assertGreater(path.stat().st_size, 0, "%s is empty" % rel)

    # ----------------------------------------------------------- the commands

    def test_published_command_runs_under_the_scripts_own_parser(self):
        command = str(self.d["command"])
        self.assertIn("research.py", command)
        self.assertNotIn("--governed", command)
        code, out = _run_main(_args_after_script(command, self.run_dir))
        self.assertEqual(code, R.EXIT["ok"], out)
        for rel in self.d["artifacts"]:
            self.assertTrue((self.run_dir / rel).is_file(), rel)

    def test_recovery_command_names_no_option_the_runner_does_not_define(self):
        recovery = str(self.d["recovery"])
        self.assertIn("research.py", recovery)
        self.assertNotIn("--governed", recovery,
                         "research.py defines no --governed option")
        code, out = _run_main(_args_after_script(recovery, self.run_dir))
        self.assertEqual(code, R.EXIT["ok"], out)

    # ---------------------------------------------- every stage's own --help

    def test_every_stage_script_answers_its_own_help(self):
        # A descriptor that resolves to nothing would be skipped by the probe,
        # so every declared script is proved to exist first.
        for stage in factory.CANONICAL_STAGES:
            script = str((factory.STAGE_DESCRIPTORS.get(stage) or {}).get("script") or "")
            self.assertTrue((ROOT / script).is_file(),
                            "stage %r script does not resolve: %r" % (stage, script))
        problems = factory.validate_registry(help_probe=True)
        self.assertEqual(problems, [], problems)

    def test_the_help_probe_refuses_a_script_that_cannot_answer(self):
        # Negative control: the check is real, not a constant pass.
        problems = factory._help_problems(
            "probe", {"script": "scripts/core/intake_preflight/stage_commands.json"},
            ROOT)
        self.assertTrue(problems, "the --help probe accepted a non-Python file")
        self.assertIn("probe", problems[0])


if __name__ == "__main__":
    unittest.main()
