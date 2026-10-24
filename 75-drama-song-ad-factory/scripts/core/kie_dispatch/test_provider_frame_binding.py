"""Actual governed admission joins approved still bytes to provider frames.

All upload callbacks are trapped offline. No provider output is claimed and
no reservation/transport may run in these tests.
"""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))
from kie_dispatch import kie_dispatch as dispatch
from test_production_process import confirmed_run, complete_stage, approve_script, approve_storyboard
import production_process


class ProviderFrameBindingTest(unittest.TestCase):
    def setUp(self):
        # Retain pure cap checks while excluding their optional local adapter
        # audit, exactly as the existing production-process fixture does.
        for limits in {dispatch._PL, importlib.import_module('prompt_limits')}:
            audit = patch.object(limits, '_TRAIL_DONE', True)
            audit.start()
            self.addCleanup(audit.stop)
        authorized = '/Volumes/mac mini m4/Downloads/git trees and automations'
        assert tempfile.gettempdir().startswith(authorized), tempfile.gettempdir()
        self.temp = tempfile.TemporaryDirectory(prefix='s75-frame-binding-')
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / 'run'
        confirmed_run(self.run, song=False)
        for stage in ('research', 'creative-strategy', 'script-lyrics'):
            complete_stage(self.run, stage)
        approve_script(self.run)
        for stage in ('music', 'continuity-bible', 'storyboard', 'image-keyframes'):
            complete_stage(self.run, stage)
        approve_storyboard(self.run)
        self.authority = production_process.admit_production(self.run, 'video-generation')
        self.assertTrue(self.authority['ok'], self.authority)
        gate = json.loads((self.run / 'storyboard/gate.json').read_text())
        prompt = 'The character takes a hopeful step in her own office. ' * 100
        self.request = {'model': 'minimax-h3/image-to-video', 'shot_id': 's1',
                        'input': {'prompt': prompt, 'duration': 4, 'resolution': '768P',
                                  'first_frame_url': 'https://example.invalid/never-approved-image.png'},
                        'storyboard': {'shots': gate['shots'][:1], 'review': gate['review']},
                        'card_receipt': {'answers': {'video_style': 'Lifelike 3D', 'audio_style': 'Soul Ballad',
                                                    'length': 120, 'video_model': 'MiniMax H3 768P'},
                                         'who': 'offline-owner-fixture', 'at': '2026-10-24'},
                        'prompt_receipt': {'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                                           'check': {'verdict': 'PASS', 'reasons': []}}}

    def submit_until_plan(self, request):
        with patch.object(dispatch.L, 'plan', return_value={'outcome': 'parked', 'reason_code': 'OFFLINE_ZERO_SPEND_TRAP', 'next_action': ''}) as plan, patch.object(dispatch.L, 'reserve', side_effect=AssertionError('no reserve')) as reserve, patch.object(dispatch, '_call', side_effect=AssertionError('no transport')) as transport, \
                patch.object(subprocess, 'run', side_effect=AssertionError('external subprocess forbidden')) as processes, \
                patch.object(subprocess, 'Popen', side_effect=AssertionError('external process forbidden')) as popen, \
                patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')) as sockets, \
                patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')) as connections:
            result = dispatch.dispatch(model=request['model'], request=request,
                                       save_dir=self.run / 'video', ledger_db=self.run / 'spend.sqlite3',
                                       run_id=self.run.name, logical_key='probe/video', attempt_id='',
                                       estimated_cost=1, prompt=request['input']['prompt'],
                                       stage='video-generation', state_store=self.run / 'control/state.sqlite3',
                                       video_job=True)
        self.assertEqual(reserve.call_count, 0)
        self.assertEqual(transport.call_count, 0)
        self.assertEqual(processes.call_count, 0, 'process/network blocker was invoked')
        self.assertEqual(popen.call_count, 0, 'process/network blocker was invoked')
        self.assertEqual(sockets.call_count, 0, 'process/network blocker was invoked')
        self.assertEqual(connections.call_count, 0, 'process/network blocker was invoked')
        return result, plan.call_count

    def uploaded(self, sid='s1'):
        seen = []
        def upload_transport(runner, adapter, args):
            self.assertEqual(args[0], 'upload')
            path = args[args.index('--file') + 1]
            seen.append(Path(path).read_bytes())
            return 0, {'data': {'download_url': 'https://fixture.invalid/uploaded-picture-' + sid + '.png'}}, ''
        # Exercise the actual default uploader path, trapping only the lower
        # transport. This is a zero-network protocol test, not a live upload.
        with patch.object(subprocess, 'run', side_effect=AssertionError('external subprocess forbidden')) as processes, \
                patch.object(subprocess, 'Popen', side_effect=AssertionError('external process forbidden')) as popen, \
                patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')) as sockets, \
                patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')) as connections:
            current_picture = importlib.import_module('lip_sync.lip_gate.picture_gate')
            actual_transport = current_picture._dispatch()
            with patch.object(actual_transport, '_call', side_effect=upload_transport):
                binding = dispatch.upload_storyboard_frame(self.run, sid)
            self.assertEqual(processes.call_count, 0, 'process/network blocker was invoked')
            self.assertEqual(popen.call_count, 0, 'process/network blocker was invoked')
            self.assertEqual(sockets.call_count, 0, 'process/network blocker was invoked')
            self.assertEqual(connections.call_count, 0, 'process/network blocker was invoked')
        self.assertEqual(len(seen), 1)
        original = Path(json.loads((self.run / 'storyboard/stills.json').read_text())[sid])
        self.assertEqual(seen[0], original.read_bytes())
        self.assertEqual(binding['sha256'], hashlib.sha256(seen[0]).hexdigest())
        return binding

    def test_unapproved_real_provider_frame_refuses_before_even_ledger_plan(self):
        result, calls = self.submit_until_plan(self.request)
        self.assertEqual(result['outcome'], 'rejected', result)
        self.assertEqual(result['reason_code'], 'PROVIDER_FRAME_UPLOAD_UNVERIFIED', result)
        self.assertEqual(calls, 0)

    def test_actual_approved_still_upload_admits_only_to_offline_plan_trap(self):
        binding = self.uploaded()
        request = deepcopy(self.request)
        request['input']['first_frame_url'] = binding['url']
        request['frame_bindings'] = {'first_frame_url': binding}
        result, calls = self.submit_until_plan(request)
        self.assertEqual(result['reason_code'], 'OFFLINE_ZERO_SPEND_TRAP', result)
        self.assertEqual(calls, 1)
        self.assertFalse(result['evidence']['accepted_production'])

    def test_another_approved_shot_or_unbound_last_frame_cannot_substitute(self):
        other = self.uploaded('s2')
        request = deepcopy(self.request)
        request['input']['first_frame_url'] = other['url']
        request['frame_bindings'] = {'first_frame_url': other}
        result, calls = self.submit_until_plan(request)
        self.assertEqual(result['reason_code'], 'PROVIDER_FRAME_SHOT_MISMATCH', result)
        self.assertEqual(calls, 0)
        binding = self.uploaded()
        request['input']['first_frame_url'] = binding['url']
        request['input']['last_frame_url'] = 'https://example.invalid/unapproved-ending.png'
        request['frame_bindings'] = {'first_frame_url': binding, 'last_frame_url': binding}
        result, calls = self.submit_until_plan(request)
        self.assertEqual(result['reason_code'], 'PROVIDER_LAST_FRAME_APPROVAL_MISSING', result)
        self.assertEqual(calls, 0)

    def test_stale_upload_metadata_or_plain_approved_label_is_not_authority(self):
        binding = self.uploaded()
        request = deepcopy(self.request)
        request['input']['first_frame_url'] = binding['url']
        request['frame_bindings'] = {'first_frame_url': binding}
        receipt = Path(binding['upload_receipt_path'])
        record = json.loads(receipt.read_text())
        record['storyboard_revision'] = 'stale-revision'
        receipt.write_text(json.dumps(record))
        result, calls = self.submit_until_plan(request)
        self.assertEqual(result['reason_code'], 'PROVIDER_FRAME_APPROVAL_STALE', result)
        self.assertEqual(calls, 0)
        request['frame_bindings'] = {'first_frame_url': {'approved': True, 'url': binding['url']}}
        result, calls = self.submit_until_plan(request)
        self.assertEqual(result['reason_code'], 'PROVIDER_FRAME_SHOT_MISMATCH', result)
        self.assertEqual(calls, 0)

    def test_custom_uploader_is_explicitly_offline_and_cannot_authorize_paid_frame(self):
        binding = dispatch.upload_storyboard_frame(self.run, 's1',
            uploader=lambda path: 'https://fixture.invalid/not-an-actual-upload.png')
        self.assertEqual(binding['execution_mode'], 'offline')
        self.assertFalse(binding['production_upload'])
        request = deepcopy(self.request)
        request['input']['first_frame_url'] = binding['url']
        request['frame_bindings'] = {'first_frame_url': binding}
        result, calls = self.submit_until_plan(request)
        self.assertEqual(result['reason_code'], 'PROVIDER_FRAME_UPLOAD_UNVERIFIED', result)
        self.assertEqual(calls, 0)

    def test_uploader_cannot_change_approved_source_or_uploaded_copy(self):
        def changing_uploader(path):
            Path(path).write_bytes(b'changed upload bytes')
            return 'https://fixture.invalid/changed.png'
        with self.assertRaises(dispatch.ProviderFrameBindingError) as caught:
            dispatch.upload_storyboard_frame(self.run, 's1', uploader=changing_uploader)
        self.assertEqual(caught.exception.code, 'PROVIDER_FRAME_CHANGED_DURING_UPLOAD')
        self.assertFalse((self.run / 'control/frame-uploads').exists())

    def test_text_to_video_and_existing_lipsync_path_have_no_new_frame_requirement(self):
        approved = self.authority['approved_storyboard']
        selected = self.request['storyboard']['shots']
        self.assertIsNone(dispatch.provider_frame_refusal('veo-3-1', {'input': {'prompt': 'text only'}}, self.run, approved, selected))
        self.assertIsNone(dispatch.provider_frame_refusal('kling/ai-avatar-standard', {'input': {'image_url': 'https://fixture.invalid/avatar'}}, self.run, approved, selected))
        request = deepcopy(self.request)
        request['input'].pop('first_frame_url')
        result, calls = self.submit_until_plan(request)
        self.assertEqual(result['reason_code'], 'PROVIDER_FRAME_REQUIRED', result)
        self.assertEqual(calls, 0)


if __name__ == '__main__':
    unittest.main()
