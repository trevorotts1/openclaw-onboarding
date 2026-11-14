#!/usr/bin/env python3
"""BU-23 acceptance test: one reader for "is the interview complete".

The decision table in interface contract 01-BUILD-SPEC.md section 2.3 is driven
by ONE fixture file (tests/fixtures/interview-status-cases.json), shared with the
TypeScript port (tests/unit/interview-status.test.ts), so the two implementations
can never agree by accident. One case per state plus the unreadable file.

Also proves the two things the Command Center and the prompt suppression rely on:
  * the CLI prints a state and exits 0, and prints UNDETERMINED with exit 1 when
    the build-state cannot be read;
  * shared-utils/interview_completion.py takes its COMPLETE word from this reader
    instead of keeping a second copy of the rule.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'interview_status.py'
FIXTURE = ROOT / 'tests' / 'fixtures' / 'interview-status-cases.json'
REGISTRY = ROOT / '23-ai-workforce-blueprint' / 'interview' / 'questions.v2.json'
STATES = {'NOT_STARTED', 'IN_PROGRESS', 'READY', 'COMPLETE', 'BUILDING', 'BUILT',
          'PLACEHOLDER', 'DECLARED', 'UNDETERMINED'}
COMPLETE_WORDS = {'COMPLETE', 'BUILDING', 'BUILT'}

sys.path.insert(0, str(ROOT / 'shared-utils'))
sys.path.insert(0, str(ROOT / 'scripts'))

import interview_status  # noqa: E402
from interview_completion import prompt_status  # noqa: E402


def load_cases():
    document = json.loads(FIXTURE.read_text(encoding='utf-8'))
    return document['cases']


class FixtureTable(unittest.TestCase):
    def test_every_state_has_a_case(self):
        covered = {case['expect'] for case in load_cases()}
        self.assertEqual(covered, STATES)

    def test_table_matches_the_fixture(self):
        for case in load_cases():
            with self.subTest(case=case['name']):
                self.assertEqual(
                    interview_status.state_of(
                        case.get('buildState'),
                        declared=case.get('declared', False),
                        gate=case.get('gate'),
                        unreadable=case.get('unreadable', False),
                    ),
                    case['expect'],
                )

    def test_a_missing_gate_can_never_invent_ready(self):
        for case in load_cases():
            if case.get('gate') is None and case.get('expect') == 'READY':
                self.fail('a READY case cannot omit the gate facts')
        self.assertEqual(interview_status.state_of({'interviewProgress': {'lastQuestionNumber': 4}}),
                         'IN_PROGRESS')

    def test_prompt_suppression_takes_its_word_from_this_reader(self):
        self.assertEqual(prompt_status({'interviewComplete': True}, {}), 'COMPLETE')
        for case in load_cases():
            if case['expect'] not in COMPLETE_WORDS:
                continue
            with self.subTest(case=case['name']):
                self.assertEqual(prompt_status(case['buildState'], {}), 'COMPLETE')


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.state = self.workspace / '.workforce-build-state.json'
        self.gate_dir = self.workspace / 'company-discovery'
        self.gate_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable, '-B', str(SCRIPT), '--state', str(self.state), *extra],
                              capture_output=True, text=True, timeout=30, env=env)

    def write_state(self, state):
        self.state.write_text(json.dumps(state), encoding='utf-8')

    def answer_everything(self):
        """Answer every registry question so the gate's complete-check passes."""
        registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
        answers = {q['id']: {'qid': q['id'], 'value': 'fixture', 'at': '2026-11-12T00:00:00Z',
                             'source': 'web'} for q in registry['questions']}
        (self.gate_dir / 'interview-gate-state.json').write_text(json.dumps({
            'version': 1, 'registryVersion': registry.get('version'), 'answers': answers,
            'skipped': [], 'unsure': [], 'attempts': {}, 'startedAt': '2026-11-12T00:00:00Z',
        }), encoding='utf-8')

    def test_ready_not_started_and_complete(self):
        self.write_state({'interviewProgress': {'lastQuestionNumber': 7}})
        self.answer_everything()
        ready = self.run_cli()
        self.assertEqual((ready.returncode, ready.stdout.strip()), (0, 'READY'), ready.stderr)

        (self.gate_dir / 'interview-gate-state.json').write_text(json.dumps({
            'version': 1, 'answers': {}, 'skipped': [], 'unsure': [], 'attempts': {},
        }), encoding='utf-8')
        self.write_state({'interviewProgress': {'lastQuestionNumber': 0}})
        fresh = self.run_cli()
        self.assertEqual((fresh.returncode, fresh.stdout.strip()), (0, 'NOT_STARTED'), fresh.stderr)

        self.write_state({'interviewComplete': True})
        (self.gate_dir / 'interview-gate-state.json').unlink()
        complete = self.run_cli('--json')
        self.assertEqual((complete.returncode, json.loads(complete.stdout)['status']),
                         (0, 'COMPLETE'), complete.stderr)

    def test_declared_flag_is_the_only_way_to_declared(self):
        self.write_state({'interviewComplete': False})
        plain = self.run_cli()
        self.assertEqual(plain.stdout.strip(), 'NOT_STARTED', plain.stderr)
        declared = self.run_cli('--declared')
        self.assertEqual((declared.returncode, declared.stdout.strip()), (0, 'DECLARED'), declared.stderr)

    def test_unreadable_build_state_is_undetermined_with_exit_1(self):
        self.state.write_text('{not json', encoding='utf-8')
        broken = self.run_cli()
        self.assertEqual((broken.returncode, broken.stdout.strip()), (1, 'UNDETERMINED'), broken.stderr)
        self.state.unlink()
        missing = self.run_cli('--json')
        self.assertEqual((missing.returncode, json.loads(missing.stdout)['status']),
                         (1, 'UNDETERMINED'), missing.stderr)

    def test_unreadable_registry_is_undetermined_not_not_started(self):
        self.write_state({'interviewProgress': {'lastQuestionNumber': 2}})
        unreadable = self.run_cli('--registry', str(self.workspace / 'absent-registry.json'))
        self.assertEqual((unreadable.returncode, unreadable.stdout.strip()),
                         (1, 'UNDETERMINED'), unreadable.stderr)
        self.write_state({'interviewComplete': True})
        still_complete = self.run_cli('--registry', str(self.workspace / 'absent-registry.json'))
        self.assertEqual(still_complete.stdout.strip(), 'COMPLETE', still_complete.stderr)


if __name__ == '__main__':
    unittest.main()
