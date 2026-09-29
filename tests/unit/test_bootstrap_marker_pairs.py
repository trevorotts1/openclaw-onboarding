#!/usr/bin/env python3
"""BEGIN/END marker pairs in AGENTS.md: compaction pairs them, the Skill 38
stamper heals an orphaned END-only stanza instead of appending a duplicate.

Seen on a client box: AGENTS.md carried Skill 38 stanzas whose BEGIN line was
gone (body + `<!-- END SKILL38: X -->` only). The stamper could not see them, so
every run appended a fresh copy next to each orphan and AGENTS.md went over its
60,000-character budget; bootstrap-validate-daily failed every day.

  * compact-bootstrap.py parse(): MARKER_RE labels a BEGIN line "BEGIN X" and an
    END line "X", so no BEGIN-prefixed pair ever matched and every such span
    stopped one line short of its END. Pairs now match and the span covers END.
  * 05-update-agents-md.sh: an END-only stanza under the stanza's own heading is
    removed with its body and rewritten once; a stray END under someone else's
    heading loses only the END line.

Run: python3 tests/unit/test_bootstrap_marker_pairs.py
"""
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STAMPER = REPO / "38-conversational-ai-system" / "scripts" / "05-update-agents-md.sh"
NAME = "STEP_0_5_QUIET_HOURS"
BEGIN, END = "<!-- BEGIN SKILL38: %s -->" % NAME, "<!-- END SKILL38: %s -->" % NAME


def _compact():
    spec = importlib.util.spec_from_file_location("compact_pairs", REPO / "scripts" / "compact-bootstrap.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CompactPairs(unittest.TestCase):
    def test_well_formed_pairs_span_through_their_end_line(self):
        parse = _compact().parse
        for begin, end in (("<!-- BEGIN SKILL38: X -->", "<!-- END SKILL38: X -->"),
                           ("<!-- BEGIN skill:44-demo:agents -->", "<!-- END skill:44-demo:agents -->")):
            text = "# A\n\n%s\n## Owned block\nbody\n%s\n\n## Cold\ntext\n" % (begin, end)
            lines = text.splitlines()
            _, spans, covered, _ = parse(text)
            self.assertEqual([(s, e) for s, e, _ in spans], [(lines.index(begin), lines.index(end))], begin)
            self.assertTrue(covered[lines.index(end)], end)


class StamperOrphans(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)
        (self.tmp / "home").mkdir()
        self.agents = self.tmp / "AGENTS.md"
        self.agents.write_text("# Bootstrap\n\n## PRIME DIRECTIVE\nYou are the agent.\n")
        self.stamp()

    def stamp(self):
        env = dict(os.environ, HOME=str(self.tmp / "home"), AGENTS_MD=str(self.agents),
                   SKILL38_MASTER_FILES_DIR=str(self.tmp / "mf"),
                   SKILL38_COREFILE_VAULT=str(self.tmp / "vault"))
        r = subprocess.run(["bash", str(STAMPER)], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def heading(self):
        lines = self.agents.read_text().splitlines()
        return lines[lines.index(BEGIN) + 1]

    def test_orphaned_end_only_stanza_is_healed_not_duplicated(self):
        heading = self.heading()
        self.agents.write_text(self.agents.read_text().replace(BEGIN + "\n", "", 1))  # the lost BEGIN
        out = self.stamp()
        text = self.agents.read_text()
        self.assertEqual((text.count(BEGIN), text.count(END), text.count(heading + "\n")), (1, 1, 1))
        self.assertIn("1 orphaned END-only stanza", out)
        size = len(text)
        self.stamp()                                       # idempotent: no growth on the next run
        self.assertEqual(len(self.agents.read_text()), size)

    def test_stray_end_under_an_owner_heading_keeps_the_owner_text(self):
        text = self.agents.read_text().replace(BEGIN + "\n", "", 1)
        start = text.index(self.heading())
        text = text[:start] + "## Owner notes\nkeep me\n" + text[text.index(END):]  # the stanza body is gone too
        self.agents.write_text(text)
        self.stamp()
        text = self.agents.read_text()
        self.assertIn("## Owner notes\nkeep me\n", text)
        self.assertEqual((text.count(BEGIN), text.count(END)), (1, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
