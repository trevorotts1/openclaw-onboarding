"""Regression tests for false completion. Fixtures never certify real deployment."""
import contextlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/social-completion-audit.py'
spec = importlib.util.spec_from_file_location('social_completion_v2', SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
RELEASE = {'ONB': 'a' * 40, 'CC': 'b' * 40}
CANDIDATE, BASE, BATCH, TREE = 'c' * 40, 'd' * 40, 'e' * 40, 'f' * 40
DIFF = audit.digest(b'actual git diff bytes')


class Provider:
    """Injected independent proof provider, not a CLI offline bypass."""
    def __init__(self):
        self.overrides = {}
        self.file_bytes = b'1.2.3 release marker fixture\n'
        self.workflow_source = {'name': 'released-fixture', 'settings': {'executionOrder': 'v1'},
            'nodes': [
                {'id': 'trigger', 'name': 'Trigger', 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
                 'position': [0, 0], 'parameters': {'path': 'released-route', 'httpMethod': 'POST'}},
                {'id': 'request', 'name': 'Request', 'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4,
                 'position': [200, 0], 'parameters': {'url': 'https://example.invalid/current',
                 'nodeCredentialType': 'googleDriveOAuth2Api'}, 'retryOnFail': True, 'onError': 'continueErrorOutput'},
                {'id': 'code', 'name': 'Current code', 'type': 'n8n-nodes-base.code', 'typeVersion': 2,
                 'position': [400, 0], 'parameters': {'jsCode': 'return items;'}}],
            'connections': {'Trigger': {'main': [[{'node': 'Request', 'type': 'main', 'index': 0}]]},
                            'Request': {'main': [[{'node': 'Current code', 'type': 'main', 'index': 0}]]}},
            'contract': {'fixture_only': True}}
        self.workflow_bytes = json.dumps(self.workflow_source).encode()
        self.later_refs = None

    def release(self, repo, receipt):
        result = {'main_sha': RELEASE[repo], 'tag_object': '1' * 40,
                  'tag_target': RELEASE[repo], 'released_on_main': True,
                  'tree_sha': TREE, 'tag': 'v1.2.3', 'draft': False, 'prerelease': False,
                  'release_url': f'https://github.com/{audit.REPOS[repo]}/releases/tag/v1.2.3',
                  'published_at': '2026-01-01T00:00:00Z', 'notes': 'Release notes.',
                  'ci': {'required-tests': 'success'}}
        result.update(self.overrides)
        return result

    def refs(self, repo, tag):
        return self.later_refs or {'refs/heads/main': RELEASE[repo], f'refs/tags/{tag}^{{}}': RELEASE[repo]}

    def revision(self, repo, revision, released_sha):
        return {'diff_sha256': DIFF, 'tree_sha': TREE, 'released_paths_equal': True, 'batch_paths_equal': True}

    def file(self, repo, sha, path):
        return self.workflow_bytes if path in audit.WORKFLOW_SOURCES.values() else self.file_bytes


class Packet:
    def __init__(self, root):
        self.root = Path(root)
        self.provider = Provider()
        self.when = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        self.freeze_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.review_time = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        self.put('logs/capture.txt', b'Captured command output, a test fixture only.\n')
        self.put('source/SPEC.md', b'Original fixture specification; never use as real proof.\n')
        self.put('source/COMPLETION.md', b'All obligations remain required.\n')
        scope = {'task_ids': sorted(audit.TASKS), 'accepted_design_ids': ['F02'],
                 'required_repos': {tid: ['ONB'] for tid in audit.TASKS},
                 'required_task_checks': {tid: ['positive', 'negative', 'recovery'] for tid in audit.TASKS},
                 'required_ci': {repo: ['required-tests'] for repo in audit.REPOS},
                 'required_migrations': [139, 140], 'spec': 'source/SPEC.md',
                 'completion_contract': 'source/COMPLETION.md', 'scope_approval': 'logs/capture.txt'}
        self.put('scope.v2.json', scope)
        index = {'scope': 'scope.v2.json', 'tasks': {}, 'releases': {}, 'trains': {},
                 'deployments': {}, 'workers': 'workers.json', 'waves': {}, 'scenarios': {}}
        for tid in sorted(audit.TASKS):
            path = f'tasks/{tid}.json'
            index['tasks'][tid] = path
            checks = {}
            for kind in ('positive', 'negative', 'recovery'):
                check = f'proofs/{tid}-{kind}.json'
                self.proof(check, reviewed_revisions={'ONB': CANDIDATE})
                checks[kind] = check
            revision = {'revision_id': f'{tid}-r1', 'repo': 'ONB', 'base_sha': BASE,
                        'candidate_sha': CANDIDATE, 'batch_sha': BATCH, 'tree_sha': TREE,
                        'diff_sha256': DIFF, 'paths': ['skill/file.py'], 'recorded_at': self.when,
                        'authors': [self.person('opus', 'builder')], 'reviews': [f'reviews/{tid}.json']}
            self.put(f'reviews/{tid}.json', {'reviewer': self.person('sonnet', 'qc'), 'decision': 'PASS',
                     'unresolved': [], 'revision_sha256': audit.digest(audit.canonical(revision)),
                     'recorded_at': self.when, 'transcript': 'logs/capture.txt'})
            self.put(path, {'task_id': tid, 'decision': 'PASS', 'unresolved': [],
                           'kind': 'accepted_design' if tid == 'F02' else 'implemented',
                           'required_repos': ['ONB'], 'checks': checks, 'revisions': [revision],
                           'final_revision_by_repo': {'ONB': f'{tid}-r1'}})
        for repo in audit.REPOS:
            index['releases'][repo] = f'releases/{repo}.json'
            self.proof(f'proofs/{repo}-aggregate.json', commit_sha=RELEASE[repo])
            self.put(index['releases'][repo], {'repo': repo, 'repository': audit.REPOS[repo],
                     'released_sha': RELEASE[repo], 'tree_sha': TREE, 'tag': 'v1.2.3', 'version': '1.2.3',
                     'prerelease': False, 'release_url': f'https://github.com/{audit.REPOS[repo]}/releases/tag/v1.2.3',
                     'required_ci': ['required-tests'], 'aggregate_checks': [f'proofs/{repo}-aggregate.json'],
                     'markers': [{'role': role, 'path': role, 'sha256': audit.digest(self.provider.file_bytes),
                                  'expected_token': '1.2.3'} for role in ('version', 'readme', 'changelog', 'compatibility')]})
            index['trains'][repo] = f'trains/{repo}.json'
            self.proof(f'proofs/{repo}-merge.json')
            self.put(index['trains'][repo], {'repo': repo, 'state': 'RELEASE_VERIFIED', 'candidates': [
                {'candidate_id': 'batch-1', 'task_ids': sorted(audit.TASKS), 'state': 'MERGED',
                 'released_sha': RELEASE[repo], 'merge_proof': f'proofs/{repo}-merge.json'}]})
        for profile in audit.PROFILES:
            index['deployments'][profile] = f'deployments/{profile}.json'
            checks = {}
            for check in audit.N8N_CHECKS if profile == 'n8n' else audit.HOST_CHECKS:
                path = f'proofs/{profile}-{check}.json'
                self.proof(path, environment='sandbox', target_id=profile, source_releases=RELEASE)
                checks[check] = path
            dep = {'profile': profile, 'state': 'NEW_VERSION_ACCEPTED', 'unresolved': [],
                   'rolled_back': False, 'authorized_target': True, 'target_id': profile,
                   'company_id': 'synthetic-company', 'source_releases': RELEASE, 'recorded_at': self.when,
                   'checks': checks}
            if profile == 'n8n':
                mapping = {'credential_references': {'googleDriveOAuth2Api': {'id': 'fixture-credential', 'name': 'Fixture Drive'}},
                           'webhook_prefix': 'sandbox', 'workflow_name': 'sandbox-fixture', 'approval_evidence': 'logs/capture.txt'}
                expected = {key: deepcopy(self.provider.workflow_source[key]) for key in ('name', 'nodes', 'connections', 'settings')}
                expected['name'] = 'sandbox-fixture'
                expected['nodes'][0]['parameters']['path'] = 'sandbox/released-route'
                expected['nodes'][1]['credentials'] = deepcopy(mapping['credential_references'])
                expected_hash = audit.digest(audit.canonical(expected))
                self.put('n8n/mapping.json', mapping)
                self.put('n8n/source.json', expected)
                self.put('n8n/deployed.json', {**expected, 'id': 'server-generated-id', 'active': True})
                self.proof('proofs/normalize.json', environment='sandbox', source_releases=RELEASE,
                           source_sha256=audit.digest(self.provider.workflow_bytes), canonical_sha256=expected_hash,
                           mapping_sha256=audit.digest(audit.canonical(mapping)))
                self.proof('proofs/weekly-owner.json', environment='sandbox', source_releases=RELEASE)
                dep.update({'template_id': 'synthetic-template', 'template_readback': 'logs/capture.txt',
                    'weekly_scheduler': {'kind': 'command-center-cycle-service', 'legacy_n8n_active': False,
                                         'legacy_n8n_workflow_id': 'old-weekly-id', 'single_owner': True, 'proof': 'proofs/weekly-owner.json'},
                    'workflows': {kind: {'active': True, 'workflow_id': kind, 'execution_id': 'synthetic-id',
                        'execution_result': 'success', 'source_repo_path': audit.WORKFLOW_SOURCES[kind],
                        'source_file_sha256': audit.digest(self.provider.workflow_bytes),
                        'normalization_proof': 'proofs/normalize.json', 'deployment_mapping': 'n8n/mapping.json',
                        'expected_sha256': expected_hash,
                        'source_definition': 'n8n/source.json', 'deployed_definition': 'n8n/deployed.json'}
                        for kind in ('create', 'append')}})
            else:
                dep.update({'installed_releases': RELEASE, 'migrations_applied': [139, 140],
                            'service_registered': True, 'restart_passed': True, 'persistent_state_verified': True})
            self.put(index['deployments'][profile], dep)
        self.put('workers.json', {'active_worker_count': 0, 'unfinished_worker_ids': [],
                 'max_observed_agents_by_workflow': {'wf-1': 4}, 'max_active_workflows': 1,
                 'reconciliation_log': 'logs/capture.txt'})
        for wave in range(6):
            path = f'waves/W{wave}.json'
            proof = f'proofs/W{wave}.json'
            index['waves'][f'W{wave}'] = path
            self.proof(proof)
            self.put(path, {'wave': f'W{wave}', 'state': 'REPORTED', 'report_id': f'report-{wave}',
                            'next_dispatch_id': f'dispatch-{wave+1}', 'proof': proof})
        for scenario in audit.SCENARIOS:
            path = f'proofs/scenario-{scenario}.json'
            self.proof(path, environment='sandbox', source_releases=RELEASE)
            index['scenarios'][scenario] = path
        self.put('index.v2.json', index)
        self.freeze()

    def put(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value if isinstance(value, bytes) else json.dumps(value, indent=2).encode())

    def get(self, path):
        return json.loads((self.root / path).read_text())

    def change(self, path, fn):
        value = self.get(path)
        fn(value)
        self.put(path, value)
        self.freeze()

    def proof(self, path, **fields):
        self.put(path, {'result': 'PASS', 'exit_code': 0, 'unresolved': [], 'command': 'fixture --not-live',
                        'environment': 'unit', 'recorded_at': self.when, 'artifacts': ['logs/capture.txt'], **fields})

    def person(self, family, actor):
        return {'model_family': family, 'model_id': f'claude-{family}-fixture', 'actor_id': actor, 'session_id': actor + '-session'}

    def freeze(self, final=True):
        files = {str(path.relative_to(self.root)): audit.digest(path.read_bytes())
                 for path in self.root.rglob('*') if path.is_file() and 'audit' not in path.relative_to(self.root).parts
                 and path.name != 'manifest.v2.json'}
        self.put('manifest.v2.json', {'schema_version': 2, 'program_id': audit.PROGRAM,
                 'frozen_at': self.freeze_time, 'files': files})
        if final:
            for family in ('opus', 'sonnet'):
                self.put(f'audit/final-{family}.txt', b'Independent synthetic final review transcript.\n')
                self.put(f'audit/final-{family}.v2.json', {'reviewer': self.person(family, 'final-' + family),
                    'decision': 'PASS', 'unresolved': [], 'manifest_sha256': audit.digest((self.root / 'manifest.v2.json').read_bytes()),
                    'recorded_at': self.review_time, 'transcript': f'audit/final-{family}.txt',
                    'transcript_sha256': audit.digest((self.root / f'audit/final-{family}.txt').read_bytes())})

    def result(self):
        return audit.Auditor(self.root, self.provider).run()


class CompletionRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.packet = Packet(self.temp.name)

    def rejected(self, fragment):
        result = self.packet.result()
        self.assertFalse(result['complete'], result)
        self.assertIn(fragment, '\n'.join(result['failing']))

    def test_good_fixture_passes_but_is_not_live_certification(self):
        self.assertTrue(self.packet.result()['complete'], self.packet.result()['failing'])

    def test_all_green_labels_cannot_replace_required_nested_proof(self):
        self.packet.change('proofs/n8n-create.json', lambda d: d.update(result='FAIL', exit_code=1))
        self.rejected('failed proof')

    def test_unknown_repository_rejected(self):
        self.packet.change('tasks/F01.json', lambda d: d.update(required_repos=['UNKNOWN_REPO']))
        self.rejected('repo scope changed')

    def test_forged_diff_rejected_even_with_rehashed_manifest(self):
        self.packet.change('tasks/F01.json', lambda d: d['revisions'][0].update(diff_sha256='0' * 64))
        self.rejected('forged/stale diff')

    def test_missing_f02_rejected(self):
        self.packet.change('scope.v2.json', lambda d: d['task_ids'].remove('F02'))
        self.rejected('F01-F40')

    def test_fake_candidate_sha_rejected(self):
        self.packet.change('tasks/F01.json', lambda d: d['revisions'][0].update(candidate_sha='not-a-commit'))
        self.rejected('invalid candidate_sha')

    def test_final_auditor_cannot_reuse_builder_context(self):
        path = 'audit/final-opus.v2.json'
        data = self.packet.get(path)
        data['reviewer'] = self.packet.person('opus', 'builder')
        self.packet.put(path, data)
        self.rejected('not a fresh context')

    def test_missing_required_task_check_rejected(self):
        self.packet.change('tasks/F01.json', lambda d: d['checks'].pop('recovery'))
        self.rejected('missing/changed required task checks')

    def test_wrong_remote_tag_target_rejected(self):
        self.packet.provider.overrides['tag_target'] = '9' * 40
        self.rejected('wrong target')

    def test_lightweight_tag_rejected(self):
        self.packet.provider.overrides['tag_object'] = RELEASE['ONB']
        self.rejected('annotated tag')

    def test_missing_github_release_rejected(self):
        self.packet.provider.overrides['published_at'] = None
        self.rejected('published release')

    def test_skipped_required_remote_ci_rejected(self):
        self.packet.provider.overrides['ci'] = {'required-tests': 'skipped'}
        self.rejected('required remote CI')

    def test_remote_main_does_not_contain_release_rejected(self):
        self.packet.provider.overrides['released_on_main'] = False
        self.rejected('not on remote main')

    def test_rollback_is_not_new_acceptance(self):
        self.packet.change('deployments/n8n.json', lambda d: d.update(rolled_back=True))
        self.rejected('rollback/service-restored')

    def test_inactive_new_workflow_rejected(self):
        self.packet.change('deployments/n8n.json', lambda d: d['workflows']['create'].update(active=False))
        self.rejected('inactive/unexecuted')

    def test_wrong_deployed_definition_rejected(self):
        self.packet.change('n8n/deployed.json', lambda d: d['nodes'][2]['parameters'].update(jsCode='old code;'))
        self.rejected('deployed definition differs')

    def test_identical_old_captures_and_forged_normalization_are_rejected(self):
        old = self.packet.get('n8n/source.json')
        old['nodes'][1]['parameters']['url'] = 'https://example.invalid/OLD'
        old['nodes'][2]['parameters']['jsCode'] = 'old code;'
        for path in ('n8n/source.json', 'n8n/deployed.json'):
            self.packet.put(path, old)
        old_hash = audit.digest(audit.canonical(old))
        normalization = self.packet.get('proofs/normalize.json')
        normalization['canonical_sha256'] = old_hash
        self.packet.put('proofs/normalize.json', normalization)
        dep = self.packet.get('deployments/n8n.json')
        for flow in dep['workflows'].values():
            flow['expected_sha256'] = old_hash
        self.packet.put('deployments/n8n.json', dep)
        self.packet.freeze()
        self.rejected('normalization proof not bound to released workflow/mapping')

    def test_non_json_released_source_cannot_certify_json_captures(self):
        self.packet.provider.workflow_bytes = b'not a JSON workflow'
        dep = self.packet.get('deployments/n8n.json')
        for flow in dep['workflows'].values():
            flow['source_file_sha256'] = audit.digest(self.packet.provider.workflow_bytes)
        self.packet.put('deployments/n8n.json', dep)
        self.packet.freeze()
        self.rejected('Expecting value')

    def test_role_cannot_point_to_other_released_workflow(self):
        self.packet.change('deployments/n8n.json', lambda d: d['workflows']['create'].update(source_repo_path=audit.WORKFLOW_SOURCES['append']))
        self.rejected('wrong released source')

    def test_unapproved_runtime_mapping_rejected(self):
        self.packet.change('n8n/mapping.json', lambda d: d.update(jsCode='replace all code'))
        self.rejected('unsupported deployment mapping')

    def test_changed_retry_policy_is_not_normalized_away(self):
        self.packet.change('n8n/deployed.json', lambda d: d['nodes'][1].update(retryOnFail=False))
        self.rejected('deployed definition differs')

    def test_duplicate_legacy_weekly_scheduler_rejected(self):
        self.packet.change('deployments/n8n.json', lambda d: d['weekly_scheduler'].update(legacy_n8n_active=True))
        self.rejected('legacy weekly scheduler remains active')

    def test_old_contabo_build_rejected(self):
        self.packet.change('deployments/contabo-docker.json', lambda d: d.update(installed_releases={'ONB': '0' * 40, 'CC': '0' * 40}))
        self.rejected('old/missing installed build')

    def test_unregistered_mac_service_rejected(self):
        self.packet.change('deployments/mac.json', lambda d: d.update(service_registered=False))
        self.rejected('service installation')

    def test_unit_check_cannot_certify_installed_acceptance(self):
        self.packet.change('proofs/mac-restart.json', lambda d: d.update(environment='unit'))
        self.rejected('fixture/wrong target')

    def test_missing_browser_proof_rejected(self):
        self.packet.change('index.v2.json', lambda d: d['scenarios'].pop('sheet-desktop-mobile-visual'))
        self.rejected('missing required end-to-end')

    def test_pending_worker_rejected(self):
        self.packet.change('workers.json', lambda d: d.update(active_worker_count=1))
        self.rejected('unfinished workers')

    def test_pending_candidate_rejected(self):
        self.packet.change('trains/ONB.json', lambda d: d['candidates'][0].update(state='QC_PENDING'))
        self.rejected('pending/blocked train')

    def test_empty_initial_queue_not_complete(self):
        self.packet.change('trains/ONB.json', lambda d: d.update(candidates=[]))
        self.rejected('empty initial queue')

    def test_stale_audit_after_deployment_change(self):
        dep = self.packet.get('deployments/n8n.json')
        dep['target_id'] = 'new-target'
        self.packet.put('deployments/n8n.json', dep)
        self.packet.freeze(final=False)
        self.rejected('stale final audit')

    def test_final_review_pass_with_pending_blocker_rejected(self):
        path = 'audit/final-opus.v2.json'
        data = self.packet.get(path)
        data['unresolved'] = ['n8n cutover still pending']
        self.packet.put(path, data)
        self.rejected('final audit pending/failed')

    def test_tampered_artifact_rejected_without_manifest_rewrite(self):
        self.packet.put('logs/capture.txt', b'changed after final reviews\n')
        self.rejected('evidence hash mismatch')

    def test_same_model_qc_rejected(self):
        self.packet.change('reviews/F01.json', lambda d: d.update(reviewer=self.packet.person('opus', 'other-builder')))
        self.rejected('opposite-model')

    def test_stale_repaired_revision_review_rejected(self):
        self.packet.change('tasks/F01.json', lambda d: d['revisions'][0].update(candidate_sha='9' * 40))
        self.rejected('review bound to different revision')

    def test_stale_task_test_revision_rejected(self):
        self.packet.change('proofs/F01-positive.json', lambda d: d.update(reviewed_revisions={'ONB': BASE}))
        self.rejected('task checks bind a stale')

    def test_remote_ref_race_rejected(self):
        self.packet.provider.later_refs = {'refs/heads/main': '9' * 40}
        self.rejected('remote refs changed during audit')

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            source = Path(other) / 'capture.txt'
            source.write_bytes(b'outside evidence')
            target = self.packet.root / 'logs/capture.txt'
            target.unlink()
            target.symlink_to(source)
            self.packet.freeze()
            self.rejected('escapes run root')

    def test_no_writes_by_default_and_output_refuses_overwrite(self):
        before = {str(p): p.read_bytes() for p in self.packet.root.rglob('*') if p.is_file()}
        with patch.object(audit, 'GitHubProofProvider', return_value=self.packet.provider), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, audit.main(['--run-root', str(self.packet.root)]))
            self.assertEqual(1, audit.main(['--run-root', str(self.packet.root), '--output', str(self.packet.root / 'manifest.v2.json')]))
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.packet.root.rglob('*') if p.is_file()})

    def test_legacy_packet_fails_closed(self):
        (self.packet.root / 'manifest.v2.json').unlink()
        self.rejected('manifest/scope')


class GitRevisionIntegrationTests(unittest.TestCase):
    def test_actual_git_diff_and_scoped_release_content_are_verified(self):
        with tempfile.TemporaryDirectory() as root:
            def git(*args):
                return subprocess.check_output(['git', '-C', root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', *args], stderr=subprocess.DEVNULL).decode().strip()
            git('init')
            path = Path(root) / 'file.txt'
            path.write_text('base\n')
            git('add', 'file.txt'); git('commit', '-m', 'base')
            base = git('rev-parse', 'HEAD')
            path.write_text('reviewed\n')
            git('add', 'file.txt'); git('commit', '-m', 'candidate')
            candidate = git('rev-parse', 'HEAD')
            tree = git('rev-parse', 'HEAD^{tree}')
            provider = audit.GitHubProofProvider({'ONB': root, 'CC': root})
            revision = {'base_sha': base, 'candidate_sha': candidate, 'batch_sha': candidate,
                        'tree_sha': tree, 'paths': ['file.txt']}
            actual = provider.revision('ONB', revision, candidate)
            self.assertTrue(actual['released_paths_equal'])
            self.assertEqual(tree, actual['tree_sha'])
            self.assertNotEqual(audit.digest(b''), actual['diff_sha256'])
            path.write_text('unreviewed repair\n')
            git('add', 'file.txt'); git('commit', '-m', 'repair')
            self.assertFalse(provider.revision('ONB', revision, git('rev-parse', 'HEAD'))['released_paths_equal'])


if __name__ == '__main__':
    unittest.main()
