"""Course media preserves existing appearance and never retries uncertain uploads."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import course_media
from skill6_playwright import Stop


class Api:
    def __init__(self):
        self.course = {'id':'COURSE', 'locationId':'LOC', 'updatedAt':'v1', 'title':'Keep title',
            'customizations':{'id':'READ_ONLY', 'logoImage':'https://example.com/old.png',
                'instructorName':'Keep instructor', 'settings':{'keep':True}}}
        self.calls = []
        self.lose_save = False
        self.drop_sibling = False

    def request(self, method, path, *, location_id, body=None):
        self.calls.append((method, path, location_id, deepcopy(body)))
        if method == 'PUT':
            if not self.lose_save:
                self.course.update(deepcopy(body))
                if self.drop_sibling:
                    self.course['customizations'].pop('instructorName', None)
        return deepcopy(self.course)


def capability():
    return {'location_id':'LOC', 'version':'v3', 'status':'PASS', 'source':'fixture',
        'scopes':['courses.readonly', 'courses.write', 'medias.write'],
        'checked_at':datetime.now(timezone.utc).isoformat()}


class CourseMediaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.file = self.root/'approved.png'
        self.file.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED_FIXTURE_BYTES')
        self.plan = {'location_id':'LOC', 'product_id':'COURSE', 'expected_updated_at':'v1',
            'media_assets':[{'field':'logoImage', 'file':str(self.file),
                'sha256':hashlib.sha256(self.file.read_bytes()).hexdigest(),
                'name':'Authored logo', 'expected_url':'https://example.com/old.png'}]}
        self.api = Api()
        self.uploads = []

    def upload(self, path, location, name, api):
        self.uploads.append((path.read_bytes(), location, name))
        state = json.loads((self.root/'evidence'/'delivery-state.json').read_text())
        self.assertEqual(state['current_kind'], 'media_upload')
        self.assertEqual(state['current_step_status'], 'INTENT_RECORDED')
        self.assertIs(api, self.api)
        return {'http':200, 'fileId':'MEDIA', 'url':'https://storage.example.com/new.png'}

    def run_media(self, **kwargs):
        return course_media.run_media(self.plan, self.root/'evidence',
            capability=kwargs.pop('capability', capability()), transport=self.api,
            uploader=kwargs.pop('uploader', self.upload), **kwargs)

    def test_upload_attaches_exact_bytes_preserves_customizations_and_replays_without_network(self):
        state = self.run_media()
        self.assertEqual(state['status'], 'API_STEPS_COMPLETE')
        self.assertTrue(state['verification_required'])
        self.assertIs(state['functional_verified'], False)
        self.assertEqual(self.uploads[0][0], self.file.read_bytes())
        self.assertEqual(self.uploads[0][1], 'LOC')
        custom = self.api.course['customizations']
        self.assertEqual(custom['logoImage'], 'https://storage.example.com/new.png')
        self.assertEqual(custom['instructorName'], 'Keep instructor')
        self.assertEqual(custom['settings'], {'keep':True})
        self.assertNotIn('id', next(call[3] for call in self.api.calls if call[0]=='PUT')['customizations'])
        count = len(self.api.calls)
        self.assertTrue(self.run_media()['replayed'])
        self.assertEqual(len(self.api.calls), count)
        self.assertEqual(len(self.uploads), 1)

    def test_later_bad_source_prevents_first_upload_and_any_network(self):
        self.plan['media_assets'].append({**self.plan['media_assets'][0],
            'field':'heroImage', 'sha256':'0'*64, 'expected_url':None})
        with self.assertRaisesRegex(Stop, 'approved PNG hash'):
            self.run_media()
        self.assertEqual(self.uploads, [])
        self.assertEqual(self.api.calls, [])

    def test_source_symlink_and_mutation_refuse_before_network(self):
        for mode in ('symlink', 'changed'):
            with self.subTest(mode=mode):
                if mode=='symlink':
                    linked=self.root/'linked.png';linked.symlink_to(self.file)
                    self.plan['media_assets'][0]['file']=str(linked)
                else:
                    self.plan['media_assets'][0]['file']=str(self.file)
                    self.file.write_bytes(b'\x89PNG\r\n\x1a\nCHANGED')
                with self.assertRaises(Stop):self.run_media()
                self.assertEqual(self.api.calls, [])

    def test_stale_current_url_timestamp_and_wrong_location_prevent_upload(self):
        for change in ({'updatedAt':'v2'}, {'locationId':'OTHER'},
                       {'customizations':{'logoImage':'https://example.com/different.png'}}):
            with self.subTest(change=change):
                original=deepcopy(self.api.course)
                self.api.course.update(change)
                with self.assertRaises(Stop):self.run_media()
                self.assertEqual(self.uploads, [])
                self.assertFalse(any(call[0]=='PUT' for call in self.api.calls))
                self.api.course=original

    def test_uncertain_upload_keeps_intent_and_prevents_reupload(self):
        def uncertain(*args):
            self.upload(*args)
            raise TimeoutError('uncertain upload')
        with self.assertRaises(TimeoutError):self.run_media(uploader=uncertain)
        state=json.loads((self.root/'evidence'/'delivery-state.json').read_text())
        self.assertEqual(state['status'], 'NEEDS_RECONCILIATION')
        self.assertFalse(any(call[0]=='PUT' for call in self.api.calls))
        calls=len(self.api.calls)
        with self.assertRaisesRegex(Stop, 'uncertain or unbound'):self.run_media()
        self.assertEqual(len(self.uploads), 1)
        self.assertEqual(len(self.api.calls), calls)

    def test_concurrent_edit_after_upload_stops_before_put(self):
        def concurrent(*args):
            result=self.upload(*args)
            self.api.course['customizations']['instructorName']='Other author'
            return result
        with self.assertRaisesRegex(Stop, 'changed during upload'):
            self.run_media(uploader=concurrent)
        self.assertFalse(any(call[0]=='PUT' for call in self.api.calls))
        state=json.loads((self.root/'evidence'/'delivery-state.json').read_text())
        self.assertEqual(state['uploaded_media'][0]['id'], 'MEDIA')

    def test_ignored_write_and_collateral_customization_loss_never_pass(self):
        for flag in ('lose_save', 'drop_sibling'):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as evidence:
                setattr(self.api,flag,True)
                with self.assertRaises(Stop):
                    course_media.run_media(self.plan,evidence,capability=capability(),
                        transport=self.api,uploader=lambda *args:{'http':200,'fileId':'MEDIA',
                            'url':'https://example.com/new.png'})
                self.assertEqual(json.loads(Path(evidence,'delivery-state.json').read_text())['status'],
                    'NEEDS_RECONCILIATION')
                setattr(self.api,flag,False)

    def test_media_scope_required_before_network(self):
        cap=capability();cap['scopes'].remove('medias.write')
        with self.assertRaises(Stop):self.run_media(capability=cap)
        self.assertEqual(self.api.calls, [])

    def test_host_route_validation_is_read_only_and_location_bound(self):
        data={**self.plan, 'api_capability':capability()}
        route={'operation':'courses.update','location_id':'LOC','version':'v3','lane':'public_api'}
        self.assertEqual(course_media.validate_api_inputs('courses.update',data,route)['product_id'], 'COURSE')
        for change in ({'location_id':'OTHER'}, {'version':'v2'}, {'operation':'courses.create'}, {'lane':'playwright'}):
            with self.subTest(change=change), self.assertRaises(Stop):
                course_media.validate_api_inputs('courses.update',data,{**route,**change})
        self.assertEqual(self.api.calls, [])

    def test_upload_invalid_response_or_credentials_never_reaches_put(self):
        for response in ({'http':True,'fileId':'MEDIA','url':'https://example.com/new.png'},
                         {'http':200,'fileId':'MEDIA','url':'https://user:pass@example.com/new.png'},
                         {'http':200,'fileId':'','url':'https://example.com/new.png'}):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as evidence:
                with self.assertRaises(Stop):
                    course_media.run_media(self.plan,evidence,capability=capability(),
                        transport=self.api,uploader=lambda *args:response)
                self.assertFalse(any(call[0]=='PUT' for call in self.api.calls))

    def test_tampered_completed_upload_evidence_cannot_replay(self):
        self.run_media()
        journal=self.root/'evidence'/'delivery-state.json'
        state=json.loads(journal.read_text())
        state['uploaded_media'][0]['source_sha256']='0'*64
        journal.write_text(json.dumps(state))
        calls=len(self.api.calls)
        with self.assertRaisesRegex(Stop, 'approved asset'):self.run_media()
        self.assertEqual(len(self.api.calls), calls)
        self.assertEqual(len(self.uploads), 1)

    def test_default_upload_uses_existing_write_gate_before_reused_upload(self):
        media=SimpleNamespace(GHL_SERVICES_ORIGIN='https://services.leadconnectorhq.com',
            GHL_MEDIA_UPLOAD_PATH='/medias/upload-file', upload_media=Mock())
        api=object.__new__(course_media.delivery.Skill44Transport)
        api.client=SimpleNamespace(check_write=Mock(side_effect=Stop('write refused')),
            _get_token=Mock())
        with patch.dict('sys.modules', {'ghl_media':media}):
            with self.assertRaisesRegex(Stop, 'write refused'):
                course_media._upload(self.file, 'LOC', 'Logo', api)
        media.upload_media.assert_not_called()
        api.client._get_token.assert_not_called()

    def test_dry_run_cannot_upload_or_create_an_uncertain_journal(self):
        with patch.dict('os.environ', {'CAF_DRY_RUN':'true'}):
            with self.assertRaisesRegex(Stop, 'read-only'):self.run_media()
        self.assertEqual(self.api.calls, [])
        self.assertFalse((self.root/'evidence'/'delivery-state.json').exists())


if __name__ == '__main__':
    unittest.main()
