"""Focused offline contracts; not evidence of a live page or payment."""
import unittest
import json
import tempfile
from pathlib import Path
from playwright_recipes.editor_replay import _result, completed_editor_replay
from playwright_recipes.skill6_playwright import Stop

class FrontdoorReceipts(unittest.TestCase):
    def test_row_and_responsive_receipts_bind_exact_target(self):
        row={'action':'page_layout','layout':{'section_id':'s','columns':2}}
        receipt={'status':'SAVED','section_id':'s','row_id':'r','column_ids':['a','b'],'expected_columns':2}
        self.assertEqual(_result(row,receipt,{})['row_id'],'r')
        with self.assertRaises(Stop): _result(row,dict(receipt,column_ids=['a','a']),{})
        responsive={'action':'page_responsive','responsive':{'profile':'funnel_row_width_v1','section_id':'s',
                        'row_id':'r','device':'desktop','width_percent':80}}
        proof={'status':'RESPONSIVE_SAVED','section_id':'s','row_id':'r','device':'desktop','width_percent':80}
        self.assertEqual(_result(responsive,proof,{})['width_percent'],80)
        with self.assertRaises(Stop): _result(responsive,dict(proof,width_percent=50),{})

    def test_embed_receipt_binds_original_fragment_and_iframe(self):
        step={'action':'page_embed','placement':{'section_id':'s','row_id':'r','column_id':'c'},
              'plan':{'iframe_id':'frame','approved_html_sha256':'a'*64}}
        receipt={'status':'VERIFIED','code_element_id':'code','approved_html_sha256':'a'*64,
                 'preview_url':'https://app.example/preview/page','iframe':{'iframe_id':'frame',
                    'width':400,'height':300,'visible':True,'status':'VERIFIED'}}
        self.assertEqual(_result(step,receipt,{})['code_element_id'],'code')
        with self.assertRaises(Stop): _result(step,dict(receipt,approved_html_sha256='b'*64),{})

    def test_completed_embed_journal_reaches_receipt_validation(self):
        step={'id':'embed','action':'page_embed','placement':{'section_id':'s','row_id':'r','column_id':'c'},
              'plan':{'iframe_id':'frame','approved_html_sha256':'a'*64}}
        receipt={'status':'VERIFIED','code_element_id':'code','approved_html_sha256':'a'*64,
                 'preview_url':'https://app.example/preview/page','iframe':{'iframe_id':'frame',
                    'width':400,'height':300,'visible':True,'status':'VERIFIED'}}
        job={'location_id':'loc','steps':[step]}
        old={'fingerprint':'fingerprint','location_id':'loc','status':'EDITOR_STEPS_COMPLETE',
             'current_step':'embed','current_step_status':'FINISHED','verification_required':[],
             'results':[{'id':'embed','action':'page_embed','result':receipt}]}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';path.write_text(json.dumps(old))
            self.assertEqual(completed_editor_replay(path,job,'fingerprint')['status'],'ALREADY_EXECUTED')

    def test_saved_asset_receipt_preserves_scope_and_page_inventory(self):
        stage={'action':'saved_section','saved_section':{'operation':'save','profile':'saved-assets-new',
              'scope':'template','saved_section_name':'Hero','source_section_id':'s',
              'expected_section_inventory':['s'],'expected_saved_inventory':[]}}
        proof={'status':'SAVED_ASSET_READBACK_VERIFIED','identity_kind':'unique_name_and_scope','scope':'template',
               'saved_section_name':'Hero','source_section_id':'s','section_ids':['s'],
               'native_order_forms':{},'saved_inventory':[{'name':'Hero','scope':'template'}],
               'payment_verified':False,'verification_required':True}
        self.assertEqual(_result(stage,proof,{})['saved_section_name'],'Hero')
        with self.assertRaises(Stop): _result(stage,dict(proof,scope='global'),{})

if __name__ == '__main__': unittest.main()
