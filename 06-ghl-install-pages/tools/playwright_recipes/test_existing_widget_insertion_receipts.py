"""Saved new-insertion provenance cannot be substituted with unknown reuse."""
from copy import deepcopy
import unittest

import dropdown_fields
import large_text_fields
from test_dropdown_fields import plan as dropdown_plan
from test_large_text_fields import plan as large_plan
from skill6_playwright import Stop


class InsertionReceiptTests(unittest.TestCase):
    def test_only_exact_known_new_insertion_receipts_survive_structural_aged_replay(self):
        for module,factory,key,status in ((dropdown_fields,dropdown_plan,'dropdown_fields','DROPDOWN_FIELDS_SAVED_AND_REOPENED'),
                (large_text_fields,large_plan,'large_text_fields','LARGETEXT_FIELDS_SAVED_AND_REOPENED')):
            step=factory();data=step['payload'];field=data[key][0]
            result={'status':status,'editor_url':data['start_url'],
                'fields':[{**{k:field[k] for k in ('id','field_key','data_type','native_query_key')},'placement':'added'}],
                'configuration_sha256':module.configuration_hash(step),'independent_readback':'VERIFIED',
                'behavior_verified':False,'submission_verified':False}
            with self.subTest(module=module.__name__):module.validate_receipt(result,step)
            data['field_dependencies']['observed_at']=0
            with self.subTest(aged=module.__name__):module.validate_receipt(result,step)
            reused=deepcopy(result);reused['fields'][0]['placement']='reused'
            with self.subTest(module=module.__name__,missing_reuse_proof=True),self.assertRaises(Stop):
                module.validate_receipt(reused,step)
            if module is dropdown_fields:
                reused['fields'][0]['reuse_proof']={'unique_key':field['field_key'],
                    'custom_field_name':field['name'],'query_key':field['native_query_key'],
                    'label':field['expected_label'],'options':[{'label':option} for option in field['options']]}
            else:
                reused['fields'][0]['reuse_proof']={'unique_key':field['field_key'],
                    'custom_field_name':field['name']}
            with self.subTest(module=module.__name__,positive_native_reuse_proof=True):
                module.validate_receipt(reused,step)
            malformed_reuse=deepcopy(reused);malformed_reuse['fields'][0]['reuse_proof']['unique_key']='foreign_owner'
            wrong=deepcopy(result);wrong['fields'][0]['id']='FOREIGN_API_ID'
            mutated=deepcopy(result);mutated['fields'][0]['native_query_key']='foreign_query?'
            for invalid in (malformed_reuse,wrong,mutated,{**result,'behavior_verified':True},
                            {**result,'configuration_sha256':'0'*64}):
                with self.subTest(module=module.__name__,invalid=invalid),self.assertRaises(Stop):
                    module.validate_receipt(invalid,step)


if __name__=='__main__':unittest.main()
