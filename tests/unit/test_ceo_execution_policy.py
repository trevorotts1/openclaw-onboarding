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

class PolicyTests(unittest.TestCase):
    def test_legacy_upgrade_preserves_owner_bytes(self):
        for kind in ('CEO_ORCHESTRATOR_RULE', 'CEO_ROUTING_NO_LOOPHOLES'):
            for version in (1, 2):
                with self.subTest(kind=kind, version=version):
                    start = '# SOUL.md owner title\nMy personal mission.\n---\n\n'
                    end = '\nOwner notes: keep all spaces.  \n'
                    managed = f'<!-- {kind}_V{version} -->\nLegacy router-only instructions.\n'
                    if kind == 'CEO_ROUTING_NO_LOOPHOLES' and version == 2:
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
