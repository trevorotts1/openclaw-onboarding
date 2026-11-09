"""The named host must require the real portal boundary for group details."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import community_portal as portal
import host
import recipe_cli
import skill6_playwright as core
from test_community_details import DetailsPage, details_inputs
from test_community_portal import immediate_wait, read_identity


class CommunityDetailsHostTests(unittest.TestCase):
    def probes(self):
        return {'lanes': {'playwright': {'available': True}}}

    def test_named_host_reaches_details_and_replay_does_not_write(self):
        data = details_inputs()
        page = DetailsPage(data)
        context = portal.capture_context(page, data, identity_reader=read_identity)
        with tempfile.TemporaryDirectory() as root, patch.object(portal, 'wait_until', immediate_wait):
            for _ in range(2):
                result = host.run_recipe('communities.configure', data, self.probes(), root,
                                         input_dir='.', page=page, portal_context=context)
                self.assertEqual(result['status'], 'NEEDS_VERIFICATION')
                self.assertTrue(result['result']['description_verified'])
                self.assertTrue(result['result']['protected_access_unchanged'])
            self.assertEqual(page.writes, 1)
            self.assertTrue(Path(root, 'community-details-state.json').is_file())
            self.assertNotIn(data['details']['description'], Path(root, 'community-details-state.json').read_text())

    def test_cli_check_and_missing_context_never_launch_or_seed(self):
        data = details_inputs()
        job = core.validate_job(recipe_cli.compile_recipe('communities.configure', data), Path('.'))
        self.assertEqual(job['steps'][0]['action'], 'community_details')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory, 'run')
            source = Path(directory, 'input.json'); source.write_text(json.dumps(data))
            probes = Path(directory, 'probes.json'); probes.write_text(json.dumps(self.probes()))
            output = io.StringIO()
            with redirect_stdout(output), patch.object(host, 'execute') as execute:
                code = host.main(['--operation', 'communities.configure', '--inputs', str(source),
                                  '--probes', str(probes), '--evidence-root', str(root), '--check'])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())['status'], 'PORTAL_CONTEXT_REQUIRED')
            execute.assert_not_called()
            self.assertFalse(root.exists())
            with patch.object(host, 'execute') as execute:
                result = host.run_recipe('communities.configure', data, self.probes(), root, input_dir='.')
            self.assertEqual(result['status'], 'PORTAL_CONTEXT_REQUIRED')
            execute.assert_not_called()
            with self.assertRaises(core.Stop):
                core.execute(job, root)

    def test_mixed_payload_and_foreign_location_are_rejected_before_browser(self):
        data = details_inputs()
        mixed = copy.deepcopy(data)
        mixed['channels'] = [{'name': 'Fixture', 'description': 'Fixture'}]
        with self.assertRaises(core.Stop):
            core.validate_job(recipe_cli.compile_recipe('communities.configure', mixed), Path('.'))
        job = recipe_cli.compile_recipe('communities.configure', data)
        job['steps'][0]['payload']['location_id'] = 'FOREIGN'
        with self.assertRaises(core.Stop):
            core.validate_job(job, Path('.'))


if __name__ == '__main__':
    unittest.main()
