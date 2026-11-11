#!/usr/bin/env python3
"""test_sop_lockstep.py - the SOP-LOCKED lockstep between the universal-sops funnel-craft
mirror and Skill 49 (issue 41). Fails when:
  - the AF-FUN-* codes in MASTER-FUNNEL-QC-AUTOFAIL-RULESET.md differ from
    FUNNEL-MANIFEST.json autofail_codes (either direction);
  - a gate code named in FUNNEL-PIPELINE-MANIFEST.json is not a manifest code;
  - the prover count/names in the README, SKILL.md or the pipeline manifest differ from the
    prover loop in verify.sh;
  - SKILL.md states a different AF-FUN code count than the manifest holds.
Stdlib only. Run: python3 test_sop_lockstep.py   (add --print-rows to print the mirror rows)"""
import json
import re
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SOPS = SKILL.parent / "universal-sops" / "funnel-craft"
MANIFEST = json.loads((SKILL / "FUNNEL-MANIFEST.json").read_text(encoding="utf-8"))
CODES = MANIFEST["autofail_codes"]
WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
ROW = re.compile(r"^\| (AF-FUN-[A-Z0-9-]+) \|", re.M)


def verify_provers():
    text = (SKILL / "verify.sh").read_text(encoding="utf-8")
    m = re.search(r"for p in ((?:prove_sf_\w+ ?)+); do", text)
    assert m, "verify.sh prover loop not found"
    return m.group(1).split()


def print_rows():
    for k, v in CODES.items():
        print(f"| {k} | {v['trigger'].replace('|', chr(92) + '|')} |")


class SopLockstep(unittest.TestCase):
    def test_mirror_codes_equal_manifest(self):
        text = (SOPS / "MASTER-FUNNEL-QC-AUTOFAIL-RULESET.md").read_text(encoding="utf-8")
        rows = ROW.findall(text)
        self.assertEqual(len(rows), len(set(rows)), "duplicate row in the mirror")
        mirror = set(rows)
        self.assertEqual(sorted(set(CODES) - mirror), [], "manifest codes missing from the mirror")
        self.assertEqual(sorted(mirror - set(CODES)), [], "mirror codes not in the manifest")

    def test_pipeline_manifest_gates_are_manifest_codes(self):
        pm = json.loads((SOPS / "FUNNEL-PIPELINE-MANIFEST.json").read_text(encoding="utf-8"))
        gates = set(re.findall(r"AF-FUN-[A-Z0-9-]+", json.dumps(pm.get("phases", [])) + json.dumps(pm.get("front_door_gates", []))))
        self.assertEqual(sorted(gates - set(CODES)), [])

    def test_prover_count_and_names_match_verify_sh(self):
        provers = verify_provers()
        word = WORDS[len(provers)]
        readme = (SOPS / "README.md").read_text(encoding="utf-8")
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        pm = (SOPS / "FUNNEL-PIPELINE-MANIFEST.json").read_text(encoding="utf-8")
        for name, doc in (("README", readme), ("SKILL.md", skill)):
            for p in provers:
                self.assertIn(p, doc, f"{name} does not name {p}")
            self.assertIn(f"the {word} fail-closed", doc, f"{name} does not state {len(provers)} provers")
        self.assertIn(f"(the {word} fail-closed floor provers)", pm)

    def test_skill_md_states_live_code_count(self):
        skill = " ".join((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn(f"the {len(CODES)} `AF-FUN-*` autofail codes", skill)


if __name__ == "__main__":
    if "--print-rows" in sys.argv:
        print_rows()
        sys.exit(0)
    unittest.main()
