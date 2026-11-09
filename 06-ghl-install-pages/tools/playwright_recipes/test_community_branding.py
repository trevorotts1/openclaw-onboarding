"""Modern community Branding keeps source, sibling and proof-level boundaries."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import community_branding as branding
import community_portal as portal
from skill6_playwright import Stop
from test_community_portal import Page, inputs as portal_inputs, read_identity


def inputs(path):
    data=portal_inputs();data.pop('channels')
    data['branding']={'expected':{'logo':None,'favicon':None,'cover':None},
        'images':[{'slot':'logo','file':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]}
    return data


class Control:
    def __init__(self,page,name):self.page=page;self.name=name
    def count(self):return 1
    def is_visible(self):return True
    def is_enabled(self):return True
    def wait_for(self,**kwargs):pass
    def click(self,**kwargs):
        if self.name=='Save changes':
            self.page.saves+=1
            if not self.page.lose_save:self.page.persisted=deepcopy(self.page.images)


class BrandingPage(Page):
    def __init__(self,data):
        super().__init__(data);self.images=deepcopy(data['branding']['expected'])
        self.persisted=deepcopy(self.images);self.saves=0;self.lose_save=False;self.crop=False
    def locator(self,selector):
        if selector.startswith('a[href="/communities/groups/'):
            return Control(self,'Settings')
        raise AssertionError('Unexpected fixture selector '+selector)
    def get_by_role(self,role,*,name=None,exact=None):
        if role=='button' and name in ('Save changes','Cancel'):return Control(self,name)
        return super().get_by_role(role,name=name,exact=exact)
    def goto(self,url,**kwargs):self.url=url
    def wait_for_load_state(self,*args,**kwargs):pass
    def reload(self,**kwargs):
        super().reload(**kwargs);self.images=deepcopy(self.persisted)


class CommunityBrandingTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.file=Path(self.directory.name)/'approved.png';self.file.write_bytes(b'\x89PNG\r\n\x1a\nAPPROVED')
        self.data=inputs(self.file);self.page=BrandingPage(self.data)
        self.context=portal.capture_context(self.page,self.data,identity_reader=read_identity,clock=lambda:10)
        self.root=tempfile.TemporaryDirectory();self.addCleanup(self.root.cleanup)
        self.snapshot_patch=patch.object(branding,'_snapshot',side_effect=lambda page:deepcopy(page.images))
        self.snapshot_patch.start();self.addCleanup(self.snapshot_patch.stop)
        self.dialog_patch=patch.object(branding,'_dialogs',side_effect=lambda page:page.crop)
        self.dialog_patch.start();self.addCleanup(self.dialog_patch.stop)
        def upload(page,plan,context,asset,path,clock):
            self.assertEqual(path.read_bytes(),self.file.read_bytes())
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            state=json.loads(Path(self.root.name,'community-details-state.json').read_text())
            self.assertEqual(state['status'],'INTENT_RECORDED')
            page.images[asset['slot']]='https://example.com/'+asset['slot']+'.png'
            return page.images[asset['slot']]
        self.upload_patch=patch.object(branding,'_upload',side_effect=upload)
        self.upload=self.upload_patch.start();self.addCleanup(self.upload_patch.stop)

    def run_branding(self):
        return branding.run_branding(self.page,self.data,self.root.name,portal_context=self.context,clock=lambda:11)

    def test_exact_preview_readback_keeps_sibling_images_and_pending_proof(self):
        result=self.run_branding()
        self.assertEqual(result['status'],'NEEDS_VERIFICATION')
        self.assertEqual(result['branding_slots'],['logo'])
        self.assertIsNone(self.page.images['cover']);self.assertIsNone(self.page.images['favicon'])
        self.assertFalse(result['functional_verified']);self.assertFalse(result['communication_attempted'])
        self.assertTrue(self.run_branding()['replayed']);self.assertEqual(self.upload.call_count,1)

    def test_all_file_hashes_are_checked_before_first_upload(self):
        self.data['branding']['images'].append({'slot':'cover','file':str(self.file),'sha256':'0'*64})
        with self.assertRaisesRegex(Stop,'approved PNG hash'):self.run_branding()
        self.upload.assert_not_called();self.assertEqual(self.page.saves,0)

    def test_stale_preview_refuses_before_upload(self):
        self.page.images['cover']='https://example.com/other.png'
        with self.assertRaisesRegex(Stop,'changed since inventory'):self.run_branding()
        self.upload.assert_not_called()

    def test_native_lost_save_keeps_uncertain_journal_and_blocks_reupload(self):
        self.page.lose_save=True
        with self.assertRaisesRegex(Stop,'independent preview readback'):self.run_branding()
        state=json.loads(Path(self.root.name,'community-details-state.json').read_text())
        self.assertEqual(state['status'],'RECONCILIATION_REQUIRED')
        self.assertIn('logo',state['observed_uploads'])
        with self.assertRaisesRegex(Stop,'uncertain or unbound'):self.run_branding()
        self.assertEqual(self.upload.call_count,1)

    def test_unexpected_crop_or_collateral_image_prevents_save(self):
        original=self.upload.side_effect
        def cropped(*args):
            result=original(*args);args[0].crop=True;return result
        self.upload.side_effect=cropped
        with self.assertRaisesRegex(Stop,'unexpected dialog'):self.run_branding()
        self.assertEqual(self.page.saves,0)

    def test_user_switch_and_forged_context_cannot_upload(self):
        self.page.identity['user_id']='DIFFERENT'
        with self.assertRaises(Stop):self.run_branding()
        self.upload.assert_not_called()
        self.context={'authenticated':True}
        with self.assertRaises(Stop):self.run_branding()

    def test_duplicate_slots_unsafe_url_and_unsupported_controls_refuse(self):
        data=deepcopy(self.data);data['branding']['images'].append(deepcopy(data['branding']['images'][0]))
        with self.assertRaises(Stop):branding.validate_inputs(data)
        data=deepcopy(self.data);data['branding']['expected']['cover']='javascript:bad'
        with self.assertRaises(Stop):branding.validate_inputs(data)
        data=deepcopy(self.data);data['branding']['crop']=True
        with self.assertRaises(Stop):branding.validate_inputs(data)

    def test_replay_cannot_upgrade_proof_or_change_slot_identity(self):
        self.run_branding();journal=Path(self.root.name,'community-details-state.json')
        state=json.loads(journal.read_text());state['outcome']['functional_verified']=True
        journal.write_text(json.dumps(state))
        with self.assertRaisesRegex(Stop,'saved proof'):self.run_branding()
        self.assertEqual(self.upload.call_count,1)


if __name__=='__main__':unittest.main()
