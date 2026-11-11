#!/usr/bin/env python3
"""test_sop_commands.py - every `python3 49-signature-funnel/scripts/prove_*.py ...` command line in the
funnel-craft SOPs must parse against the prover's real CLI (issue 27): each --flag exists in the
prover's --help, and the number of positional arguments is one the prover accepts. A usage-error
command in an SOP fails this test. Stdlib only. Run: python3 test_sop_commands.py"""
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
REPO = SKILL.parent
SOPS = REPO / "universal-sops" / "funnel-craft"
CMD = re.compile(r"^\s*python3\s+(49-signature-funnel/scripts/prove_\w+\.py)(.*)$")


def sop_commands():
    out = []
    for md in sorted(SOPS.glob("*.md")):
        for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            m = CMD.match(line)
            if m:
                out.append((f"{md.name}:{n}", m.group(1), shlex.split(m.group(2))))
    return out


def cli_of(script):
    """({flag: takes_value}, max_positionals) from the prover's own --help usage line."""
    r = subprocess.run([sys.executable, str(REPO / script), "--help"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(f"{script} --help failed rc={r.returncode}: {r.stderr[-300:]}")
    usage = re.split(r"\n\s*\n", r.stdout.strip(), maxsplit=1)[0]
    usage = " ".join(usage.split())
    usage = re.sub(r"^usage: \S+ ", "", usage)
    flags, positionals = {}, 0
    for grp in re.findall(r"\[[^\]]*\]|[^\s\[\]]+", usage):
        inner = grp[1:-1] if grp.startswith("[") else grp
        if inner.startswith("-"):
            for f in re.findall(r"--?[\w-]+", inner):
                flags[f] = len(inner.split()) > 1
        else:
            positionals += 1
    return flags, positionals


class SopCommands(unittest.TestCase):
    def test_commands_were_found(self):
        self.assertGreaterEqual(len(sop_commands()), 5)

    def test_every_sop_prover_command_parses(self):
        cache = {}
        for where, script, args in sop_commands():
            flags, max_pos = cache.setdefault(script, cli_of(script))
            pos, i = 0, 0
            while i < len(args):
                a = args[i]
                if a.startswith("-"):
                    self.assertIn(a, flags, f"{where}: {script} has no flag {a}")
                    i += 2 if flags[a] else 1
                else:
                    pos += 1
                    i += 1
            self.assertLessEqual(pos, max_pos, f"{where}: {script} takes at most {max_pos} positional, command has {pos}")


if __name__ == "__main__":
    unittest.main()
