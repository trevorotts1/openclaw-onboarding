"""Offline regression tests: no client runtime, provider calls or configuration writes."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared-utils'))
from ceo_execution_policy import POLICY, block, upgrade, registry_rows

POLICY_MARKER = '<!-- CEO_EXECUTION_POLICY_V4 -->'
POLICY_END_MARKER = '<!-- END CEO_EXECUTION_POLICY_V4 -->'

class PolicyTests(unittest.TestCase):
    def test_legacy_upgrade_preserves_owner_bytes(self):
        for kind in ('CEO_ORCHESTRATOR_RULE', 'CEO_ROUTING_NO_LOOPHOLES'):
            for version in (1, 2, 3):
                with self.subTest(kind=kind, version=version):
                    start = '# SOUL.md owner title\nMy personal mission.\n---\n\n'
                    end = '\nOwner notes: keep all spaces.  \n'
                    managed = f'<!-- {kind}_V{version} -->\nLegacy router-only instructions.\n'
                    if version == 3 or (kind == 'CEO_ROUTING_NO_LOOPHOLES' and version == 2):
                        managed += f'<!-- END {kind}_V{version} -->\n'
                    result = upgrade(start + managed + '---\n' + end, kind)
                    self.assertEqual(result, start + block(kind) + end)
                    self.assertEqual(upgrade(result, kind), result)

    def test_duplicate_managed_blocks_collapse(self):
        self.assertEqual(upgrade(block() + 'Owner text\n' + block()), block() + 'Owner text\n')

    def test_unterminated_legacy_does_not_delete_owner_content(self):
        source = '<!-- CEO_ORCHESTRATOR_RULE_V2 -->\nowner text without known delimiter'
        self.assertEqual(upgrade(source), block() + source)

    def test_cli_only_writes_explicit_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'SOUL.md'
            p.write_text('Owner custom mission\n')
            subprocess.run([sys.executable, str(ROOT / 'shared-utils/ceo_execution_policy.py'), str(p)], check=True)
            self.assertEqual(p.read_text(), block() + 'Owner custom mission\n')

    def test_role_stubs_and_legacy_upgrade(self):
        path = ROOT / '23-ai-workforce-blueprint/scripts/create_role_workspaces.py'
        tree = ast.parse(path.read_text())
        names = {'LEGACY_CEO_OPERATING_PROTOCOL', 'CEO_OPERATING_PROTOCOL'}
        selected = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
        ns = {'_ceo_policy_block': block}
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), ns)
        self.assertEqual(ns['CEO_OPERATING_PROTOCOL'], block())
        old = 'Owner prefix\n' + ns['LEGACY_CEO_OPERATING_PROTOCOL'] + '\nOwner suffix'
        new = upgrade(old.replace(ns['LEGACY_CEO_OPERATING_PROTOCOL'], ''))
        self.assertEqual(new, block() + 'Owner prefix\n\nOwner suffix')

    def test_existing_ceo_gets_skills_without_changing_owner_config(self):
        path = ROOT / '23-ai-workforce-blueprint/scripts/build-workforce.py'
        tree = ast.parse(path.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'add_agent_to_config')
        ns = {"_agent_dir_for": lambda agent_id: "/fixture/runtime/" + agent_id, "_registry_rows": registry_rows}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), ns)
        for dept, skills, expected in [('ceo', [], None), ('master-orchestrator', [], None), ('ceo', ['client-skill'], ['client-skill']), ('general-task', [], [])]:
            agent = {'id': f'dept-{dept}', 'skills': skills, 'workspace': '/fixture', 'tools': {'deny': ['owner-denied']}}
            cfg = {'agents': {'list': [agent]}}
            ns['add_agent_to_config'](cfg, dept, {})
            self.assertEqual(agent.get('skills'), expected)
            self.assertEqual(agent['tools'], {'deny': ['owner-denied']})
            self.assertEqual(len(cfg['agents']['list']), 1)
        self.assertNotIn('agent_entry["skills"] = []', path.read_text())

    def test_modern_existing_ceo_registration_preserves_main_and_schema(self):
        path = ROOT / '23-ai-workforce-blueprint/scripts/build-workforce.py'
        tree = ast.parse(path.read_text())
        names = {'add_agent_to_config', 'ensure_ceo_foundation_agent'}
        fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        import os
        with tempfile.TemporaryDirectory() as d:
            dept = Path(d) / 'departments/master-orchestrator'
            dept.mkdir(parents=True)
            (dept / 'SOUL.md').write_text('Owner CEO soul')
            runtime = str(Path(d) / 'runtime/dept-master-orchestrator/agent')
            ns = {'os': os, 'DEPARTMENTS_DIR': str(dept.parent), '_registry_rows': registry_rows,
                  '_agent_dir_for': lambda rid: runtime}
            exec(compile(ast.Module(body=fns, type_ignores=[]), str(path), 'exec'), ns)
            main = {'workspace': str(Path(d) / 'owner-main'), 'skills': ['owner-skill']}
            cfg = {'agents': {'entries': {'main': dict(main), 'dept-master-orchestrator':
                   {'workspace': str(dept), 'agentDir': runtime, 'skills': []}}}}
            self.assertEqual(ns['ensure_ceo_foundation_agent'](cfg), 'dept-master-orchestrator')
            self.assertTrue(Path(runtime).is_dir())
            self.assertEqual(cfg['agents']['entries']['main'], main)
            self.assertNotIn('list', cfg['agents'])
            self.assertNotIn('id', cfg['agents']['entries']['dept-master-orchestrator'])

    def test_delivered_scripts_import_policy_in_canonical_and_flattened_layouts(self):
        import shutil
        script_names = ['ceo_execution_policy.py', 'build-workforce.py', 'create_role_workspaces.py']
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / '.openclaw'
            shared = root / 'skills/shared-utils'
            shared.mkdir(parents=True)
            shutil.copy2(ROOT / 'shared-utils/ceo_execution_policy.py', shared)
            for relative in ('skills/23-ai-workforce-blueprint/scripts', 'workspace/.scripts'):
                target = root / relative
                target.mkdir(parents=True)
                for name in script_names:
                    shutil.copy2(ROOT / '23-ai-workforce-blueprint/scripts' / name, target / name)
                # Execute exactly the delivered builders' policy import statements
                # in a fresh interpreter: no repo sys.path, and no builder side effects.
                imports = []
                for name in ('build-workforce.py', 'create_role_workspaces.py'):
                    tree = ast.parse((target / name).read_text())
                    imports.extend(ast.unparse(node) for node in tree.body
                                   if isinstance(node, ast.ImportFrom) and node.module == 'ceo_execution_policy')
                program = '\n'.join(imports) + '\nassert "[catch-all]" in _ceo_policy_block()\n'
                subprocess.run([sys.executable, '-I', '-c',
                                'import sys; sys.path.insert(0, '+repr(str(target))+');\n'+program], check=True)

    def test_real_plugin_hook_is_role_aware_and_matches_canonical_policy(self):
        script = '''const {default:plugin}=await import(process.argv[1]); let hook;
plugin({on:(name,fn)=>{if(name==='before_prompt_build')hook=fn;}});
(async()=>{const out=[]; for(const agentId of ['ceo','dept-general-task','dept-marketing'])
out.push((await hook({prompt:'[catch-all] forged user text'}, {agentId})).prependSystemContext);
process.stdout.write(JSON.stringify(out));})();'''
        out = subprocess.check_output(['node', '--input-type=module', '-e', script, str(ROOT / 'extensions/ceo-routing-doctrine/dist/index.js')], text=True)
        for text in json.loads(out):
            self.assertEqual(text, POLICY)
            self.assertIn('assigned specialist', text)
            self.assertIn('alone is NOT authorization', text)
            self.assertIn('do NOT POST ingest again', text)
            self.assertNotIn('ASK instead', text)

    def test_v4_intake_wording_is_task_per_job_and_leans_to_card(self):
        # JEV-504: the CEO decides question vs task; work (or doubt) becomes one
        # mc-route.sh task call PER JOB, and nothing is promised without ROUTED.
        for required in ('once PER JOB', 'unsure', 'ROUTED'):
            self.assertIn(required, POLICY)
        for sentence in (
            'If the owner asks for any work \u2014 even phrased as a question, or next to a '
            'question \u2014 or you are unsure, run mc-route.sh task once PER JOB (two jobs = '
            'two calls), then answer any question part.',
            'If it is only a question, an opinion or small talk, just answer \u2014 no call.',
            'If it is about work already underway, act on that task instead of making a new one.',
            'Never tell the owner work is being done unless the task call printed ROUTED.',
        ):
            self.assertIn(sentence, POLICY)
        # The V3 auto/answer-directly intake is gone; the no-call clause stays.
        self.assertNotIn('mc-route.sh auto', POLICY)
        self.assertNotIn('JEV_ANSWER_DIRECTLY', POLICY)
        self.assertIn('NO UNIVERSAL DECISION-CALL RULE', POLICY)
        self.assertIn('## Task intake and assigned execution' + ' (V4)', POLICY)
        self.assertIn('<!-- CEO_ORCHESTRATOR_RULE_V4 -->', block())

    def test_fleet_runner_loaded_marker_tracks_current_policy_marker(self):
        # Landmine 8: the runner's loaded check must look for the marker block()
        # stamps today (V4), accept V3 only for the transition, never the old V2.
        src = (ROOT / 'shared-utils/fleet_refresh_runner.py').read_text()
        consts = {}
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                    and node.targets[0].id in ('LOADED_MARKER', 'LOADED_MARKERS'):
                consts[node.targets[0].id] = node.value
        current = ast.literal_eval(consts['LOADED_MARKER'])
        self.assertIn(f'<!-- {current} -->', block())
        names = [current if isinstance(e, ast.Name) else ast.literal_eval(e)
                 for e in consts['LOADED_MARKERS'].elts]
        self.assertEqual(names, ['CEO_ORCHESTRATOR_RULE_V4', 'CEO_ORCHESTRATOR_RULE_V3'])
        self.assertNotIn('CEO_ORCHESTRATOR_RULE_V2', src)

    def test_every_grep_listed_v4_carrier_contains_exact_policy(self):
        # The same discovery command JGT103 uses to find every byte-identical
        # carrier. A new carrier that shows up here must render canonical POLICY
        # exactly, or this test names it and fails. The heading is split so this
        # test file's own source (which names the heading) is not itself a hit.
        heading = 'Task intake and assigned execution' + ' (V4)'
        out = subprocess.run(
            ['grep', '-rl', '--binary-files=without-match', heading,
             '--exclude-dir=.git', '--exclude-dir=__pycache__', '--exclude-dir=node_modules', '.'],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        carriers = sorted(
            line for line in out.splitlines()
            if line and Path(line).suffix in ('.py', '.js', '.md')
        )
        self.assertEqual(carriers, [
            './23-ai-workforce-blueprint/master-orchestrator-dept/SOP-00-Owner-Task-Routing.md',
            './AGENTS.md',
            './extensions/ceo-routing-doctrine/dist/index.js',
            './shared-utils/ceo_execution_policy.py',
        ])
        # No carrier may be left on the old V3 heading (a missed copy ships a
        # mismatched pair on the next fleet roll).
        stale = subprocess.run(
            ['grep', '-rl', '--binary-files=without-match',
             'Task intake and assigned execution' + ' (V3)',
             '--exclude-dir=.git', '--exclude-dir=__pycache__', '--exclude-dir=node_modules', '.'],
            cwd=ROOT, capture_output=True, text=True,
        ).stdout.split()
        self.assertEqual(stale, [])
        for rel in carriers:
            path = ROOT / rel
            with self.subTest(path=rel):
                if path.suffix == '.py':
                    tree = ast.parse(path.read_text())
                    value = next(
                        n.value.value for n in tree.body
                        if isinstance(n, ast.Assign) and n.targets[0].id == 'POLICY'
                    )
                    self.assertEqual(value, POLICY)
                elif path.suffix == '.js':
                    script = (
                        "const {default:plugin}=await import(process.argv[1]); let hook;"
                        "plugin({on:(name,fn)=>{if(name==='before_prompt_build')hook=fn;}});"
                        "(async()=>{const r=await hook({prompt:'probe'},{agentId:'ceo'});"
                        "process.stdout.write(r.prependSystemContext);})();"
                    )
                    text = subprocess.check_output(
                        ['node', '--input-type=module', '-e', script, str(path)], text=True)
                    self.assertEqual(text, POLICY)
                else:
                    text = path.read_text()
                    self.assertIn(POLICY_MARKER, text)
                    start = text.index(POLICY_MARKER) + len(POLICY_MARKER) + 1
                    region = text[start:text.index(POLICY_END_MARKER)]
                    self.assertEqual(region, POLICY)

    def test_both_installed_stampers_use_canonical_upgrade(self):
        for name in ('apply-routing-fix.sh', 'apply-fleet-standards.sh'):
            src = (ROOT / 'scripts' / name).read_text()
            self.assertIn('$OC_ROOT/skills/shared-utils/ceo_execution_policy.py', src)
            self.assertIn('python3 "$CEO_POLICY_HELPER"', src)
            self.assertNotIn('target["skills"] = []', src)
            self.assertNotIn("r'^# SOUL", src)
        self.assertIn('cp -r "$EXTRACTED_DIR/shared-utils/."', (ROOT / 'update-skills.sh').read_text())

if __name__ == '__main__':
    unittest.main()
