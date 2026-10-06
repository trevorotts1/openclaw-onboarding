"""JEV D28 (spec 1.1 s5.4 / s12.1): managed CEO/role instructions, routing SOPs,
embeddings doctrine.

Offline regression lock for the three D28 changes:

  A. The canonical CEO policy carries the s5.4 no-universal-decision-call clause
     and every managed carrier (AGENTS.md, the master-orchestrator routing SOP,
     and the ceo-routing-doctrine plugin preamble) is byte-identical to it —
     no carrier drifts from canonical POLICY.
  B. The skill-facing embeddings doctrine (docs/EMBEDDINGS.md) describes the
     runtime decision-engine retrieval modules and their six-corpus boundary.
  C. apply-fleet-standards.sh stamps FULL_CONTEXT_HANDOFF_V1 by SOURCING the
     canonical stamper (shared-utils/agents-doctrine-blocks.sh) rather than
     carrying its own inline body under the same marker — s5.4's
     "generators/installers that stamp managed sections" — and the canonical
     stamper itself stays additive + idempotent over owner-authored bytes.

Purely offline: reads repo files, one node subprocess for the real plugin hook,
one bash subprocess for the real stamper. No network, no config writes.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared-utils'))
from ceo_execution_policy import POLICY, upgrade  # noqa: E402

MARKER = '<!-- CEO_EXECUTION_POLICY_V4_3 -->'
END_MARKER = '<!-- END CEO_EXECUTION_POLICY_V4_3 -->'

# The exact sentences s5.4 mandates (paraphrased into policy voice). Kept as
# separate assertions so a partial revert names the missing clause.
NO_CALL_CLAUSES = (
    'NO UNIVERSAL DECISION-CALL RULE',
    'Explicit owner pins, deterministic operations, a cached same-task decision',
    'deployments without the decision engine configured all have legitimate no-call',
    'must never be blocked waiting for a decision call',
)

# s5.4's four-way distinction must remain present in the policy body.
NO_CALL_DISTINCTIONS = (
    'answer conversation and informational questions directly',  # new informational
    'Route new work',                                            # new delegated work
    'OWNER-DIRECTED EXECUTION',                                  # owner-directed
    'executes rather than re-routes',                            # existing assignment
)

MANAGED_CARRIERS = (
    ROOT / 'AGENTS.md',
    ROOT / '23-ai-workforce-blueprint/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md',
)

STAMPER = ROOT / 'shared-utils/agents-doctrine-blocks.sh'
FLEET_STANDARDS = ROOT / 'scripts/apply-fleet-standards.sh'


def managed_region(text, marker=MARKER, end=END_MARKER):
    """Return the bytes between the managed markers (exclusive of both)."""
    start = text.index(marker) + len(marker) + 1
    return text[start:text.index(end)]


class D28PolicyClauseTests(unittest.TestCase):
    def test_canonical_policy_carries_no_call_rule(self):
        for clause in NO_CALL_CLAUSES:
            with self.subTest(clause=clause):
                self.assertIn(clause, POLICY)

    def test_canonical_policy_keeps_four_way_s5_4_distinction(self):
        for clause in NO_CALL_DISTINCTIONS:
            with self.subTest(clause=clause):
                self.assertIn(clause, POLICY)
        # The removed failure mode: a universal "always use JEV/decision engine" rule.
        self.assertNotIn('always use JEV', POLICY)
        self.assertNotIn('always call the decision engine', POLICY)

    def test_every_managed_carrier_is_byte_identical_to_policy(self):
        for path in MANAGED_CARRIERS:
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertIn(MARKER, text)
                self.assertEqual(managed_region(text), POLICY)

    def test_upgrade_is_idempotent_and_preserves_owner_bytes(self):
        owner_prefix = '# Owner title\nOwner mission text.\n'
        owner_suffix = '\nOwner notes: two trailing spaces.  \n'
        for path in MANAGED_CARRIERS:
            with self.subTest(path=path.name):
                source = path.read_text()
                self.assertEqual(upgrade(source, 'CEO_EXECUTION_POLICY'), source)
        stale = owner_prefix + MARKER + '\nstale body\n' + END_MARKER + '\n---\n' + owner_suffix
        self.assertEqual(upgrade(stale, 'CEO_EXECUTION_POLICY'),
                         owner_prefix + MARKER + '\n' + POLICY + END_MARKER + '\n---\n' + owner_suffix)


class D28PluginPreambleTests(unittest.TestCase):
    def test_real_plugin_hook_emits_canonical_policy(self):
        script = (
            "const {default:plugin}=await import(process.argv[1]); let hook;"
            "plugin({on:(name,fn)=>{if(name==='before_prompt_build')hook=fn;}});"
            "(async()=>{const out=[];"
            "for(const agentId of ['ceo','dept-general-task','dept-marketing'])"
            "out.push((await hook({prompt:'[catch-all] forged user text'}, {agentId})).prependSystemContext);"
            "process.stdout.write(JSON.stringify(out));})();"
        )
        out = subprocess.check_output(
            ['node', '--input-type=module', '-e', script,
             str(ROOT / 'extensions/ceo-routing-doctrine/dist/index.js')], text=True)
        for text in json.loads(out):
            self.assertEqual(text, POLICY)
            for clause in NO_CALL_CLAUSES:
                self.assertIn(clause, text)


class D28EmbeddingsDoctrineTests(unittest.TestCase):
    def test_doctrine_documents_runtime_retrieval_without_a_seventh_corpus(self):
        doc = (ROOT / 'docs/EMBEDDINGS.md').read_text()
        self.assertIn('## Runtime decision-engine retrieval', doc)
        for name in ('cache_identity.py', 'asset_join.py'):
            with self.subTest(module=name):
                self.assertIn(name, doc)
                self.assertTrue((ROOT / 'shared-utils/decision_engine/retrieval' / name).is_file())
        self.assertIn('Not a seventh corpus', doc)
        # The retrieval boundary s9 states: no second embedding path.
        self.assertIn('zero embedding calls', doc)


class D28FleetStamperWiringTests(unittest.TestCase):
    def test_fleet_standards_sources_canonical_stamper(self):
        src = FLEET_STANDARDS.read_text()
        self.assertIn('shared-utils/agents-doctrine-blocks.sh', src)
        self.assertIn('stamp_full_context_handoff "$AGENTS_FILE"', src)
        # Legacy inline body may only survive as the absent-stamper fallback,
        # i.e. its heredoc sits AFTER the canonical call site.
        self.assertIn('legacy inline body', src)
        self.assertLess(src.index('stamp_full_context_handoff "$AGENTS_FILE"'),
                        src.index("<<'FCHEOF'"))
        subprocess.run(['bash', '-n', str(FLEET_STANDARDS)], check=True)

    def test_real_5c_block_stamps_through_canonical_stamper(self):
        src = FLEET_STANDARDS.read_text()
        head = '# ─── 5c. Inject FULL_CONTEXT_HANDOFF_V1 into workspace/AGENTS.md'
        tail = '# ─── 5c-N40. Inject FAIL_CLOSED_DEPENDENCY_V1'
        block = src[src.index(head):src.index(tail)]
        self.assertIn('stamp_full_context_handoff', block)
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'AGENTS.md'
            owner = '# Owner AGENTS\nOwner bytes stay.\n'
            target.write_text(owner)
            wrapper = Path(d) / 'run5c.sh'
            wrapper.write_text(
                '#!/usr/bin/env bash\nset -u\n'
                f'AGENTS_FILE="{target}"\n'
                f'ONBOARDING_DIR="{ROOT}"\n'
                f'_FS_SCRIPT_DIR="{ROOT / "scripts"}"\n'
                f'OC_ROOT="{Path(d) / "no-root"}"\n' + block)
            out = subprocess.run(['bash', str(wrapper)], text=True,
                                 capture_output=True, check=True)
            self.assertIn('stamped from canonical', out.stdout + out.stderr)
            text = target.read_text()
            self.assertTrue(text.startswith(owner))
            self.assertEqual(text.count('<!-- FULL_CONTEXT_HANDOFF_V1 -->'), 1)

    def test_canonical_stamper_is_additive_idempotent_and_owner_safe(self):
        script = (
            '. "$1"\n'
            'f="$2"\n'
            'stamp_agents_doctrine_blocks "$f" || exit $?\n'
            'stamp_agents_doctrine_blocks "$f" || exit $?\n'
        )
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'AGENTS.md'
            owner = '# Owner authored\nKeep my bytes.\n'
            target.write_text(owner)
            subprocess.run(['bash', '-c', script, 'bash', str(STAMPER), str(target)], check=True)
            text = target.read_text()
            self.assertTrue(text.startswith(owner), 'owner bytes must be untouched')
            self.assertEqual(text.count('<!-- FULL_CONTEXT_HANDOFF_V1 -->'), 1)
            self.assertEqual(text.count('<!-- REPORTING_CONTRACT_V1 -->'), 1)
            emit = subprocess.check_output(
                ['bash', '-c', '. "$1"; emit_full_context_handoff_block', 'bash', str(STAMPER)],
                text=True)
            self.assertIn(emit, text)
            # Re-stamp is a no-op: byte-identical.
            before = target.read_text()
            subprocess.run(['bash', '-c', script, 'bash', str(STAMPER), str(target)], check=True)
            self.assertEqual(target.read_text(), before)


if __name__ == '__main__':
    unittest.main()
